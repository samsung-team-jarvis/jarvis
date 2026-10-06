"""kitchen_gw 실행.

python -m services.kitchen_gw                                  # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.kitchen_gw send ON hood                     # 명령 하나를 보내고 결과를 본다
python -m services.kitchen_gw send LEVEL burner_1 3
python -m services.kitchen_gw.fake_kitchen                     # Unity 대신 답하는 가짜 가상 주방
"""

from __future__ import annotations

import argparse
import datetime
import signal
import sys
import threading

from common import kitchen_link as link
from common.bus import connect
from common.messages import Envelope
from services.kitchen_gw.service import KitchenGateway


def show(msg: Envelope) -> None:
    p = msg.payload
    state = "확인됨" if p["ok"] else f"실패({p.get('reason', '')})"
    print(f"[control/result] seq={p['seq']} {state} 재전송 {p['retries']}회 {p['rtt_ms']:.1f} ms")


def send(args: argparse.Namespace) -> int:
    """개발용: 안전 판단 서비스 대신 `control/command` 하나를 버스에 올리고 결과를 본다."""
    value = {"ON": 1, "OFF": 0}.get(args.command, args.value)
    seq = int(datetime.datetime.now().timestamp() * 1000) % 1_000_000
    command = {"seq": seq, "cmd": args.command, "target": args.target, "value": value}
    link.validate_command(command)
    bus = connect(args.bus, client_id="kitchen_gw_send")
    done = threading.Event()
    results: list[Envelope] = []

    def on_result(msg: Envelope) -> None:
        if msg.payload["seq"] == seq:
            results.append(msg)
            done.set()

    bus.subscribe("control/result", on_result)
    session_id = f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus.publish(Envelope.new("control/command", "kitchen_gw_send", command, session_id))
    got = done.wait(timeout=3)
    bus.close()
    if not got:
        print("결과가 오지 않았습니다 — kitchen_gw가 떠 있는지 확인하세요")
        return 1
    show(results[0])
    return 0 if results[0].payload["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="버스와 가상 주방 사이에서 메시지를 옮긴다")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument(
        "--session", default=None, help="온도·heartbeat session_id (생략 시 s_<시각>)"
    )
    parser.add_argument("--quiet", action="store_true", help="결과를 낼 때마다 출력하지 않음")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("send", help="control/command 하나를 보내고 결과를 기다린다 (개발용)")
    p.add_argument("command", choices=link.CMDS)
    p.add_argument("target")
    p.add_argument("value", nargs="?", type=int, default=1, help="LEVEL일 때 세기 1~3")
    args = parser.parse_args()
    if args.cmd == "send":
        return send(args)

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="kitchen_gw")
    gateway = KitchenGateway(bus, session_id, on_result=None if args.quiet else show)
    gateway.start()
    print("kitchen_gw 시작: control/command 구독 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.05):
            gateway.poll()
            gateway.heartbeat()
    except KeyboardInterrupt:
        pass
    bus.close()
    print(
        f"OK: control/result {gateway.results}건 (실패 {gateway.failed}건), "
        f"sensor/reading {gateway.readings}건"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
