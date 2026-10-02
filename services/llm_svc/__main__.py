"""llm_svc 실행 (v0: 규칙 파서만).

python -m services.llm_svc                               # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.llm_svc --bus mqtt://localhost:1883
python -m services.llm_svc parse "후드 세게 틀어 줘"       # 버스 없이 파서 결과만 보기
"""

from __future__ import annotations

import argparse
import datetime
import json
import signal
import sys
import threading

from common.bus import connect
from common.function_call import to_tokens
from common.messages import Envelope
from services.llm_svc.rule_parser import parse
from services.llm_svc.service import LlmService


def show(msg: Envelope) -> None:
    p = msg.payload
    print(f"[llm/function_call] {p['raw_text']!r} → {json.dumps(p['call'], ensure_ascii=False)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="stt/text를 명령(Function Call)으로 바꿔 발행한다")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("parse", help="버스 없이 문장 하나를 파싱해 출력")
    p.add_argument("text")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="heartbeat session_id (생략 시 s_<시각>)")
    parser.add_argument("--quiet", action="store_true", help="발행할 때마다 출력하지 않음")
    args = parser.parse_args()

    if args.cmd == "parse":
        call = parse(args.text)
        print(json.dumps(call, ensure_ascii=False))
        print(to_tokens(call))
        return 0

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="llm_svc")
    service = LlmService(bus, session_id, on_call=None if args.quiet else show)
    service.start()
    print("llm_svc(규칙 파서) 시작: stt/text 구독 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.2):
            service.heartbeat()
    except KeyboardInterrupt:
        pass
    bus.close()
    print(
        f"OK: llm/function_call {service.published}건 발행 (호출어 없어 무시 {service.ignored}건)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
