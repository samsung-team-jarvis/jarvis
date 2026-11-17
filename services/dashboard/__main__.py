"""dashboard 실행 (UI-01): 버스 → `kitchen/overlay`.

python -m services.dashboard              # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.dashboard --print      # 바뀔 때마다 화면 정보를 터미널에도 출력 (로컬 화면 대신)
"""

from __future__ import annotations

import argparse
import datetime
import signal
import sys
import threading
from typing import Any

from common.bus import connect
from services.dashboard.service import Overlay

NAMES = {"burner_1": "1번 화구", "burner_2": "2번 화구", "fryer": "튀김기"}


def show(o: dict[str, Any]) -> None:
    heaters = " · ".join(
        f"{NAMES.get(k, k)} {'켜짐' if v['on'] else '꺼짐'}"
        + (f" {v['temperature_c']:.0f}°C" if v.get("temperature_c") is not None else "")
        for k, v in o["heaters"].items()
    )
    lines = [f"[{o['state_text']}] risk={o['risk']}  {heaters}  사람={o['person']}"]
    if o["heard"]:
        lines.append(f"  들은 말: {o['heard']}")
    if o["reply"] or o["reason"]:
        lines.append(f"  판단: {o['decision']} {o['reply'] or ''} {o['reason'] or ''}".rstrip())
    if o["warning"]:
        lines.append(f"  ⚠ {o['warning']}")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="화면에 겹쳐 띄울 정보를 가상 주방으로 보낸다")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="heartbeat session_id (생략 시 s_<시각>)")
    parser.add_argument("--print", action="store_true", help="바뀔 때마다 터미널에 출력")
    args = parser.parse_args()

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="dashboard")
    overlay = Overlay(bus, session_id, on_overlay=show if args.print else None)
    overlay.start()
    print("dashboard 시작: kitchen/overlay로 화면 정보 전송 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.2):
            overlay.tick()
            overlay.heartbeat()
    except KeyboardInterrupt:
        pass
    bus.close()
    print(f"OK: kitchen/overlay {overlay.published}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
