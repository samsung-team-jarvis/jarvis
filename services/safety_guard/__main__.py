"""safety_guard 실행 (v0: 규칙 판정 + 결제 확인 + 긴급 빠른 경로).

python -m services.safety_guard                         # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.safety_guard --assume-state COOKING  # 상황 인식 없이 개발할 때 (가정 상태)
python -m services.safety_guard judge '{"action":"TURN_ON","target":"burner_1"}' --state DANGER
"""

from __future__ import annotations

import argparse
import datetime
import json
import signal
import sys
import threading

from common.bus import connect
from common.messages import Envelope
from services.safety_guard.rules import STATES, judge
from services.safety_guard.service import SafetyGuard


def show(msg: Envelope) -> None:
    p = msg.payload
    reason = f" ({p['reason']})" if p["reason"] else ""
    print(f"[guard/decision] {json.dumps(p['call'], ensure_ascii=False)} → {p['decision']}{reason}")


def main() -> int:
    parser = argparse.ArgumentParser(description="명령을 판정해 허용된 것만 제어 명령으로 발행한다")
    sub = parser.add_subparsers(dest="cmd")
    j = sub.add_parser("judge", help="버스 없이 명령 하나를 판정해 출력")
    j.add_argument("call", help='Function Call JSON, 예: \'{"action":"TURN_ON","target":"hood"}\'')
    j.add_argument("--state", choices=STATES, default=None, help="생략 시 상태 모름")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="heartbeat session_id (생략 시 s_<시각>)")
    parser.add_argument(
        "--assume-state",
        choices=STATES,
        default=None,
        help="fusion/state를 받기 전의 가정 상태 (개발용). 생략하면 상태 모름 = 화구 켜기 거부",
    )
    parser.add_argument("--quiet", action="store_true", help="판정할 때마다 출력하지 않음")
    args = parser.parse_args()

    if args.cmd == "judge":
        d = judge(json.loads(args.call), args.state)
        print(f"{d.decision} {d.reason}".strip())
        return 0

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="safety_guard")
    guard = SafetyGuard(
        bus, session_id, assume_state=args.assume_state, on_decision=None if args.quiet else show
    )
    guard.start()
    state = args.assume_state or "모름 (fusion/state 대기)"
    print(f"safety_guard 시작: 상태={state}, llm/function_call·stt/text 구독 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.2):
            guard.heartbeat()
    except KeyboardInterrupt:
        pass
    bus.close()
    c = guard.counts
    print(
        f"OK: 허용 {c['ALLOW']} · 거부 {c['REJECT']} · 확인 질문 {c['ASK']}"
        f" · 긴급 빠른 경로 {c['fast_path']}"
        f" · 중복 긴급 정지 무시 {c['duplicate']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
