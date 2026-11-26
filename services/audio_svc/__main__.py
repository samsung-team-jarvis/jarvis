"""audio_svc 실행: 음성 → VAD → SenseVoice → `stt/text` 발행.

python -m services.audio_svc                                  # 마이크 (Ctrl+C로 종료)
python -m services.audio_svc --input data/stt/cmds.wav --realtime --bus mqtt://localhost:1883
python -m services.audio_svc --input data/stt/cmds.wav --bus memory://   # 기다리지 않고 확인만
python -m services.audio_svc --tts-out data/tts --no-play     # 음성 응답을 소리 없이 wav로만
"""

from __future__ import annotations

import argparse
import datetime
import signal
import sys
import threading
from collections.abc import Callable

from common.bus import connect
from common.messages import Envelope
from services.audio_svc.responses import KitchenStatus, RiskWatcher, reply_for_decision
from services.audio_svc.self_test import SelfTest
from services.audio_svc.service import AudioService
from services.audio_svc.sources import mic_chunks, wav_chunks
from services.audio_svc.speaker import Speaker
from services.audio_svc.stt import LANGUAGES, SenseVoice, model_dir_from_env
from services.audio_svc.tts import KoreanTts, tts_model_dir_from_env
from services.audio_svc.vad import Segmenter, VadConfig, vad_model_from_env
from services.audio_svc.wake import split_wake


def show(msg: Envelope) -> None:
    p = msg.payload
    lag_ms = round((msg.mono - p["speech_end_mono"]) * 1000)
    timing = f"음성 {p['audio_ms']} ms · STT {p['stt_ms']} ms · 발화 끝→발행 {lag_ms} ms"
    if p["wake"]:
        print(f"[stt/text] 명령 {split_wake(p['text'])!r} ← {p['text']!r} ({timing})")
    else:
        print(f"[stt/text] 무시(호출어 없음) {p['text']!r} ({timing})")


# 사용자 명령에 대한 응답이 아닌 판정 (자동 차단·긴급 빠른 경로) — 대화 모드를 열지 않는다
_NOT_USER_REASONS = ("자동 차단", "긴급 빠른 경로")
# 실행이 아닌 응답 — 대화 모드를 열지 않는다 (지원 외 응답 뒤 잡담이 계속 명령이 되지 않게)
_NO_FOLLOWUP_ACTIONS = ("UNSUPPORTED", "EMERGENCY_STOP", "CONFIRM", "DENY")


def followup_kind(payload: dict) -> bool | None:
    """guard/decision 뒤 호출어 없이 받을지.

    True=되묻기(앞 명령과 합침), False=대화 모드, None=받지 않음.
    """
    action = payload["call"].get("action")
    reason = payload.get("reason") or ""
    if reason.startswith(_NOT_USER_REASONS) or action in _NO_FOLLOWUP_ACTIONS:
        return None
    if action == "ASK_CLARIFY":
        return True
    return False if payload["decision"] == "ALLOW" else None


def start_speaker(
    args: argparse.Namespace, bus, on_followup: Callable[[bool], None] | None = None
) -> Speaker | None:
    """guard/decision·fusion/state(·device/state)를 구독해 음성으로 응답한다.

    TTS 모델이 없으면 응답 없이 진행.
    """
    try:
        tts = KoreanTts(args.tts_model_dir or tts_model_dir_from_env(), args.tts_threads)
    except FileNotFoundError as e:
        print(f"경고: 음성 응답 없이 진행합니다 — {e}", file=sys.stderr)
        return None
    speaker = Speaker(
        tts,
        play=not args.no_play,
        out_dir=args.tts_out,
        on_spoken=lambda text, sec: print(f"[tts] {text!r} ({sec:.1f} s)"),
    )
    watcher = RiskWatcher()
    status = KitchenStatus()  # 상태·위험 확인에 답할 마지막 상태 (STT-13)

    def on_decision(msg: Envelope) -> None:
        if text := reply_for_decision(msg.payload, status):
            speaker.say(text)
            if on_followup and (merge := followup_kind(msg.payload)) is not None:
                on_followup(merge)  # 되묻기 대답·대화 모드는 호출어 없이 받는다 (#STT-14)

    def on_state(msg: Envelope) -> None:
        status.on_state(msg.payload)
        if text := watcher.update(msg.payload):
            speaker.say(text)

    bus.subscribe("guard/decision", on_decision)
    bus.subscribe("fusion/state", on_state)
    bus.subscribe("device/state", lambda msg: status.on_devices(msg.payload))
    return speaker


def main() -> int:
    parser = argparse.ArgumentParser(description="음성을 받아써서 stt/text로 발행한다")
    parser.add_argument("--input", default="mic", help="mic 또는 wav 파일 경로 (16kHz 16-bit)")
    parser.add_argument("--device", default=None, help="마이크 장치 번호·이름 (생략 시 기본 장치)")
    parser.add_argument(
        "--realtime", action="store_true", help="wav를 실제 속도로 흘림 (지연 측정용)"
    )
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="session_id (생략 시 s_<시각>)")
    parser.add_argument(
        "--model-dir", default=None, help="생략 시 JARVIS_STT_MODEL_DIR 또는 기본 폴더"
    )
    parser.add_argument("--vad-model", default=None, help="생략 시 JARVIS_VAD_MODEL 또는 기본 경로")
    parser.add_argument(
        "--min-silence",
        type=float,
        default=VadConfig.min_silence_s,
        help="이만큼 조용하면 발화 끝 (초, 짧을수록 빠르지만 말 중간에서 끊길 수 있다)",
    )
    parser.add_argument(
        "--pre-roll", type=float, default=VadConfig.pre_roll_s, help="구간 앞에 더 붙이는 길이 (초)"
    )
    parser.add_argument("--language", default="ko", choices=LANGUAGES)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--quiet", action="store_true", help="발행할 때마다 출력하지 않음")
    tts = parser.add_argument_group("음성 응답 (STT-12)")
    tts.add_argument("--no-tts", action="store_true", help="음성 응답 끄기")
    tts.add_argument("--no-play", action="store_true", help="스피커로 재생하지 않음")
    tts.add_argument("--tts-out", default=None, help="응답 음성을 wav로 저장할 폴더")
    tts.add_argument("--tts-model-dir", default=None, help="생략 시 JARVIS_TTS_MODEL_DIR 또는 기본")
    tts.add_argument("--tts-threads", type=int, default=2, help="TTS CPU 스레드 (특강 p.34)")
    args = parser.parse_args()

    try:
        stt = SenseVoice(
            args.model_dir or model_dir_from_env(), language=args.language, num_threads=args.threads
        )
        config = VadConfig(min_silence_s=args.min_silence, pre_roll_s=args.pre_roll)
        segmenter = Segmenter(args.vad_model or vad_model_from_env(), config)
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if args.input == "mic":
        device = int(args.device) if args.device and args.device.isdigit() else args.device
        chunks = mic_chunks(device=device, stop=stop)
    else:
        chunks = wav_chunks(args.input, realtime=args.realtime)

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="audio_svc")
    services: list[AudioService] = []  # 응답(speaker)이 서비스보다 먼저 만들어져서 나중에 채운다

    def on_followup(merge: bool) -> None:
        if services:
            services[0].expect_reply(merge)

    speaker = None if args.no_tts else start_speaker(args, bus, on_followup=on_followup)
    # 시연 화면의 마이크·스피커 테스트 버튼 (UI-04)
    self_test = SelfTest(bus, session_id, speaker, on_event=lambda t: print(f"[audio/test] {t}"))
    self_test.start()
    service = AudioService(
        stt,
        segmenter,
        bus,
        session_id,
        on_text=None if args.quiet else show,
        mute=speaker.is_muted if speaker else None,
        on_chunk=self_test.feed,
    )
    services.append(service)
    print(f"audio_svc 시작: input={args.input} session={session_id} (Ctrl+C로 종료)")
    code = 0
    try:
        service.run(chunks)
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        code = 1
    bus.close()
    if speaker:
        speaker.close()  # 남은 응답을 마저 읽고 끝낸다
    if code:
        return code
    print(
        f"OK: stt/text {service.published}건 발행 (호출 {service.published - service.ignored} · "
        f"호출어 없어 무시 {service.ignored}) · 빈 결과 {service.skipped}건 건너뜀"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
