"""fusion_svc 실행 (State Machine v1).

python -m services.fusion_svc              # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.fusion_svc --quiet      # State가 바뀔 때마다 출력하지 않음
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
from services.fusion_svc.service import TOPICS, FusionService


def show(msg: Envelope) -> None:
    p = msg.payload
    e = p["evidence"]
    temps = {
        k: v["temperature_c"] for k, v in e["heaters"].items() if v["on"] or v["temperature_c"]
    }
    stale = f" 끊김={','.join(e['stale'])}" if e["stale"] else ""
    print(
        f"[fusion/state] {p['prev_state']} → {p['state']} (risk={p['risk']}) "
        f"온도={json.dumps(temps)} 사람={e['person']} 비움={e['absent_s']}s{stale}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="근거를 묶어 주방 State를 판정해 발행한다")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="session_id (생략 시 s_<시각>)")
    parser.add_argument("--quiet", action="store_true", help="State가 바뀔 때마다 출력하지 않음")
    args = parser.parse_args()

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="fusion_svc")
    service = FusionService(bus, session_id, on_state=None if args.quiet else show)
    service.start()
    print(f"fusion_svc 시작: {', '.join(TOPICS)} 구독 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.2):
            service.tick()
            service.heartbeat()
    except KeyboardInterrupt:
        pass
    bus.close()
    print(f"OK: fusion/state {service.published}건 (State 바뀜 {service.changes}번)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
