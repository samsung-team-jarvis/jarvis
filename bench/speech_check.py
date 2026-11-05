"""잡음 세기별 STT와 TTS 명료도 (STT-11 · STT-12).

python -m bench.speech_check noise data/stt/manifest.csv   # val, 원음 · 20 · 10 · 5 · 0 dB
python -m bench.speech_check tts                            # 응답 문장 VITS 합성 → 되받아쓰기
python -m bench.speech_check tts --engine say               # 비교: macOS 음성 (보드 불가, 참고)

noise — 매니페스트 발화에 백색 잡음을 SNR(신호 대 잡음비)별로 섞어 받아쓴다.
  파일을 통째로 받아쓰므로 서비스의 VAD 경로가 아니고, 실제 주방 소음도 아니다
  — 실제 소음 녹음(STT-05)이 생기면 그것을 기준으로 한다.
  SNR 0 dB = 말과 잡음의 세기가 같다. 난수 시드를 고정해 같은 잡음으로 다시 잰다.
tts — 음성 응답 문장(`services/audio_svc/responses.py`)을 합성해 SenseVoice로 다시 받아쓴
  CER(되받아쓰기)로 알아듣기 쉬움을 대신 잰다. STT 오류도 섞이므로 같은 STT로 잰
  다른 TTS와 비교해서 본다.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile
import time
import wave

import jiwer
import numpy as np

from bench.stt_eval import load_manifest, normalize
from services.audio_svc.responses import ASK_QUESTIONS, RISK_WARNINGS, describe, reply_for_decision
from services.audio_svc.wake import is_wake

SNRS_DB = (None, 20, 10, 5, 0)  # None = 원음
SEED = 0


def mix_at_snr(signal: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """`signal`에 `noise`를 SNR `snr_db`가 되게 키워 더한다 (평균 전력 기준, [-1, 1]로 자름)."""
    p_signal = float(np.mean(signal.astype(np.float64) ** 2))
    p_noise = float(np.mean(noise.astype(np.float64) ** 2))
    if p_signal == 0 or p_noise == 0:
        return signal.astype(np.float32)
    scale = np.sqrt(p_signal / (p_noise * 10 ** (snr_db / 10)))
    return np.clip(signal + noise * scale, -1.0, 1.0).astype(np.float32)


def response_sentences() -> list[str]:
    """시연에서 실제로 나오는 응답 문장 (장치 조작 · 타이머 · 결제 · 거절 · 되묻기 · 위험 경고)."""
    calls = [
        {"action": "TURN_ON", "target": "hood"},
        {"action": "TURN_ON", "target": "burner_1"},
        {"action": "TURN_OFF", "target": "burner_2"},
        {"action": "TURN_OFF", "target": "all"},
        {"action": "SET_LEVEL", "target": "burner_2", "level": 1},
        {"action": "SET_LEVEL", "target": "fryer", "level": 3},
        {"action": "SET_LEVEL", "target": "light", "level": 3},
        {"action": "SET_LEVEL", "target": "music", "level": 1},
        {"action": "SET_TIMER", "target": "fryer", "duration_s": 180},
        {"action": "SET_TIMER", "duration_s": 90},
        {"action": "CANCEL_TIMER"},
        {"action": "EMERGENCY_STOP"},
        {"action": "UNSUPPORTED"},
        {"action": "REQUEST_PAYMENT"},
        {"action": "DENY"},
    ]
    sentences = [describe(c) for c in calls]
    sentences.append(reply_for_decision({"call": {"action": "REQUEST_PAYMENT"}, "decision": "ASK"}))
    for target, reason in (
        ("fryer", "온도가 너무 높아요. 끄려면 꺼 달라고 말해 주세요."),
        ("burner_1", "긴급 정지 상태예요. 안전을 확인한 뒤 다시 말해 주세요."),
    ):
        call = {"action": "TURN_ON", "target": target}
        sentences.append(reply_for_decision({"call": call, "decision": "REJECT", "reason": reason}))
    sentences += [*ASK_QUESTIONS.values(), *RISK_WARNINGS.values()]
    return [s for s in sentences if s]


def run_noise(args, stt) -> int:
    from services.audio_svc.stt import read_wav

    items = load_manifest(args.manifest, args.split)
    if not items:
        print("평가할 발화가 없습니다 (--split 확인).", file=sys.stderr)
        return 1
    rng = np.random.default_rng(SEED)
    clips = []
    for item in items:
        samples, rate = read_wav(args.root / item["path"])
        clips.append((item, samples, rate, rng.standard_normal(len(samples)).astype(np.float32)))
    n_wake = sum(is_wake(item["transcript"]) for item, *_ in clips)
    print(f"## 잡음 세기별 STT — {args.manifest} (split={args.split}, {len(clips)}발화, 백색 잡음)")
    print()
    print("| SNR | CER | 호출어 인식 | RTF |")
    print("|---|---|---|---|")
    for snr in args.snr:
        refs, hyps, stt_ms, audio_ms, woke = [], [], 0, 0, 0
        for item, samples, rate, noise in clips:
            x = samples if snr is None else mix_at_snr(samples, noise, snr)
            result = stt.transcribe(x, rate)
            refs.append(normalize(item["transcript"]))
            hyps.append(normalize(result.text))
            stt_ms, audio_ms = stt_ms + result.stt_ms, audio_ms + result.audio_ms
            woke += is_wake(item["transcript"]) and is_wake(result.text)
        label = "원음" if snr is None else f"{snr:g} dB"
        cer = jiwer.cer(refs, hyps) * 100
        print(f"| {label} | {cer:.1f}% | {woke} / {n_wake} | {stt_ms / audio_ms:.3f} |", flush=True)
    return 0


def synthesize_say(text: str, voice: str) -> tuple[np.ndarray, int, float]:
    """macOS `say` → (샘플, 16000, 합성 초)."""
    from services.audio_svc.stt import read_wav

    with tempfile.TemporaryDirectory() as tmp:
        aiff, wav = pathlib.Path(tmp) / "a.aiff", pathlib.Path(tmp) / "a.wav"
        start = time.monotonic()
        subprocess.run(["say", "-v", voice, "-o", aiff, text], check=True)
        took = time.monotonic() - start
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", aiff, wav], check=True
        )
        samples, rate = read_wav(wav)
    return samples, rate, took


def save_wav(path: pathlib.Path, samples: np.ndarray, rate: int) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def run_tts(args, stt) -> int:
    from services.audio_svc.tts import KoreanTts, clean, tts_model_dir_from_env

    if args.engine == "vits":
        tts = KoreanTts(args.tts_model_dir or tts_model_dir_from_env(), args.tts_threads)
        tts.synthesize("준비")  # 첫 호출 준비 시간은 빼고 잰다

        def synth(text):
            start = time.monotonic()
            samples, rate = tts.synthesize(text)
            return samples, rate, time.monotonic() - start

    else:

        def synth(text):
            return synthesize_say(text, args.voice)

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, text in enumerate(response_sentences()):
        samples, rate, took = synth(text)
        heard = stt.transcribe(samples, rate).text
        rows.append((text, took, len(samples) / rate, heard))
        if args.out:
            save_wav(args.out / f"{i:02d}.wav", samples, rate)
    refs = [normalize(clean(text)) for text, *_ in rows]
    hyps = [normalize(heard) for *_, heard in rows]
    synth_s = [took for _, took, _, _ in rows]
    audio_s = [dur for _, _, dur, _ in rows]
    exact = sum(a == b for a, b in zip(refs, hyps, strict=True))
    print(f"## TTS 되받아쓰기 — {args.engine} ({len(rows)}문장)")
    print()
    print("| 합성 시간 (평균 · 최대) | 음성 길이 평균 | RTF | 되받아쓰기 CER | 글자까지 같음 |")
    print("|---|---|---|---|---|")
    print(
        f"| {np.mean(synth_s) * 1000:.0f} · {max(synth_s) * 1000:.0f} ms "
        f"| {np.mean(audio_s):.1f} s | {sum(synth_s) / sum(audio_s):.3f} "
        f"| {jiwer.cer(refs, hyps) * 100:.1f}% | {exact} / {len(rows)} |"
    )
    print()
    print("| 문장 | 되받아쓴 결과 |")
    print("|---|---|")
    for (text, *_, heard), ref, hyp in zip(rows, refs, hyps, strict=True):
        if ref != hyp:
            print(f"| {text} | {heard} |")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="잡음 세기별 STT, TTS 되받아쓰기")
    sub = parser.add_subparsers(dest="cmd", required=True)
    noise = sub.add_parser("noise", help="매니페스트 발화 + 백색 잡음 → CER · 호출어 · RTF")
    noise.add_argument("manifest", type=pathlib.Path)
    noise.add_argument("--root", type=pathlib.Path, default=pathlib.Path("data"))
    noise.add_argument("--split", default="val", help="조정 근거는 val (기본)")
    noise.add_argument(
        "--snr",
        type=lambda v: None if v == "clean" else float(v),
        nargs="+",
        default=list(SNRS_DB),
        help="SNR dB 목록, clean = 원음 (기본: clean 20 10 5 0)",
    )
    tts = sub.add_parser("tts", help="응답 문장 합성 → 되받아쓰기 CER · 합성 시간")
    tts.add_argument("--engine", choices=["vits", "say"], default="vits")
    tts.add_argument("--voice", default="Yuna", help="--engine say의 목소리 (macOS)")
    tts.add_argument("--tts-model-dir", default=None)
    tts.add_argument("--tts-threads", type=int, default=2)
    tts.add_argument("--out", type=pathlib.Path, default=None, help="합성 wav를 저장할 폴더")
    for p in (noise, tts):
        p.add_argument("--model-dir", default=None, help="STT 모델 (생략 시 기본)")
        p.add_argument("--threads", type=int, default=4, help="STT CPU 스레드")
    args = parser.parse_args()

    from services.audio_svc.stt import SenseVoice, model_dir_from_env

    stt = SenseVoice(args.model_dir or model_dir_from_env(), "ko", args.threads)
    return run_noise(args, stt) if args.cmd == "noise" else run_tts(args, stt)


if __name__ == "__main__":
    sys.exit(main())
