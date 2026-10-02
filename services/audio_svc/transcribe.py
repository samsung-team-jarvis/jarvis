"""wav 파일 받아쓰기 (STT-01).

python -m services.audio_svc.transcribe data/stt/sample.wav
python -m services.audio_svc.transcribe a.wav b.wav --language auto --model-dir ~/voice/models/...
"""

from __future__ import annotations

import argparse
import sys
import time

from services.audio_svc.stt import LANGUAGES, SenseVoice, model_dir_from_env


def main() -> int:
    parser = argparse.ArgumentParser(description="SenseVoice로 wav 파일을 받아쓴다")
    parser.add_argument("wavs", nargs="+", help="16-bit PCM wav (16kHz mono 권장)")
    parser.add_argument(
        "--model-dir", default=None, help="생략 시 JARVIS_STT_MODEL_DIR 또는 models/ 기본 폴더"
    )
    parser.add_argument("--language", default="ko", choices=LANGUAGES)
    parser.add_argument("--threads", type=int, default=4, help="CPU 스레드 수 (보드 기본 4)")
    parser.add_argument("--no-itn", action="store_true", help="숫자·문장부호 정규화(ITN) 끄기")
    args = parser.parse_args()

    model_dir = args.model_dir or model_dir_from_env()
    start = time.monotonic()
    try:
        stt = SenseVoice(
            model_dir, language=args.language, num_threads=args.threads, use_itn=not args.no_itn
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    load_ms = round((time.monotonic() - start) * 1000)
    print(f"모델 로드 {load_ms} ms ({model_dir}, language={args.language})")

    for path in args.wavs:
        try:
            result = stt.transcribe_file(path)
        except (OSError, ValueError) as e:
            print(f"오류: {e}", file=sys.stderr)
            return 1
        print(f"{path}: {result.text}")
        print(f"  audio {result.audio_ms} ms · stt {result.stt_ms} ms · RTF {result.rtf:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
