"""녹화기 실행 / 녹화 파일 요약.

python -m services.recorder                          # 모든 토픽을 data/sessions/에 녹화
python -m services.recorder --out data/sessions --bus mqtt://localhost:1883
python -m services.recorder summary data/sessions/<세션>.jsonl
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import threading

from common.bus import connect
from services.recorder.store import SessionWriter, summarize

DEFAULT_OUT = "data/sessions"  # .gitignore 대상


def record(args: argparse.Namespace) -> int:
    writer = SessionWriter(args.out)
    bus = connect(args.bus, client_id="recorder")
    bus.subscribe(args.topic, writer.write)
    print(f"녹화 중: topic={args.topic} → {writer.out_dir}/<session_id>.jsonl (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        stop.wait()
    except KeyboardInterrupt:
        pass
    bus.close()
    writer.close()
    for (session, topic), n in sorted(writer.counts.items()):
        print(f"  {session}  {topic}: {n}")
    print(f"OK: {sum(writer.counts.values())}건 녹화")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="버스 메시지를 세션별 JSONL로 녹화한다")
    sub = parser.add_subparsers(dest="cmd")
    s = sub.add_parser("summary", help="녹화 파일 요약")
    s.add_argument("files", nargs="+")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--topic", default="#", help="녹화할 토픽 패턴 (기본: 전부)")
    args = parser.parse_args()

    if args.cmd == "summary":
        for f in args.files:
            print(json.dumps(summarize(f), ensure_ascii=False, indent=2))
        return 0
    return record(args)


if __name__ == "__main__":
    sys.exit(main())
