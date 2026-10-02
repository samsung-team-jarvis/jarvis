"""문장 하나를 TTS로 읽기 (STT-12 확인용).

python -m services.audio_svc.speak "후드를 켰습니다."                 # 스피커로
python -m services.audio_svc.speak "후드를 켰습니다." --out a.wav --no-play  # 소리 없이 파일로
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

from services.audio_svc.speaker import save_wav, sounddevice_player
from services.audio_svc.tts import KoreanTts, tts_model_dir_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="문장을 한국어 TTS로 읽는다")
    parser.add_argument("text")
    parser.add_argument("--out", type=pathlib.Path, default=None, help="wav로 저장")
    parser.add_argument("--no-play", action="store_true", help="스피커로 재생하지 않음")
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    try:
        tts = KoreanTts(args.model_dir or tts_model_dir_from_env(), args.threads, args.speed)
    except FileNotFoundError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    start = time.monotonic()
    samples, rate = tts.synthesize(args.text)
    gen_ms = round((time.monotonic() - start) * 1000)
    print(f"합성 {gen_ms} ms · 길이 {len(samples) / rate:.2f} s · {rate} Hz")
    if args.out:
        save_wav(args.out, samples, rate)
        print(f"저장: {args.out}")
    if not args.no_play:
        sounddevice_player(samples, rate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
