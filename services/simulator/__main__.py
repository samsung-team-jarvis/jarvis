"""시뮬레이터 실행.

python -m services.simulator services/simulator/scenarios/overheat.yaml --bus mqtt://localhost:1883
python -m services.simulator <시나리오> --speed 10        # 10배속
python -m services.simulator <시나리오> --speed 0 --bus memory://   # 대기 없이 (확인용)
"""

from __future__ import annotations

import argparse
import datetime
import sys

from common.bus import connect
from common.messages import Envelope
from services.simulator.runner import play
from services.simulator.scenario import ScenarioError, load


def main() -> int:
    parser = argparse.ArgumentParser(description="시나리오대로 가짜 메시지를 버스에 발행한다")
    parser.add_argument("scenario")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--speed", type=float, default=1.0, help="재생 배속 (0이면 대기 없이)")
    parser.add_argument("--session", default=None, help="session_id (생략 시 sim_<이름>_<시각>)")
    parser.add_argument("--quiet", action="store_true", help="메시지마다 출력하지 않음")
    args = parser.parse_args()

    try:
        sc = load(args.scenario)
    except (ScenarioError, OSError) as exc:
        print(f"시나리오 오류: {exc}")
        return 1

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = args.session or f"sim_{sc.name}_{stamp}"

    def show(msg: Envelope) -> None:
        if msg.type != "system/heartbeat":
            print(f"[{msg.type}] {msg.payload}")

    bus = connect(args.bus, client_id="simulator")
    print(f"재생: {sc.name} ({sc.duration_s:g}s, {args.speed:g}배속) session={session_id}")
    count = play(sc, bus, session_id, speed=args.speed, on_event=None if args.quiet else show)
    bus.close()
    print(f"OK: {count}건 발행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
