"""가짜 publisher / subscriber 예제 — 버스가 동작하는지 확인할 때 쓴다.

python -m common.demo selftest --bus memory://        # 한 프로세스 안에서 보내고 받기
python -m common.demo sub --bus mqtt://localhost:1883  # 터미널 1: 모든 토픽 출력
python -m common.demo pub --bus mqtt://localhost:1883  # 터미널 2: 가짜 메시지 발행
"""

from __future__ import annotations

import argparse
import sys
import threading
import time

from common.bus import connect
from common.messages import Envelope

SESSION = "s_demo"


def fake_messages() -> list[Envelope]:
    return [
        Envelope.new("system/heartbeat", "demo_pub", {"alive": True}, SESSION),
        Envelope.new(
            "stt/text",
            "demo_pub",
            {
                "text": "자비스 후드 켜줘",
                "wake": True,
                "audio_ms": 1800,
                "stt_ms": 120.0,
                "speech_end_mono": time.monotonic(),
            },
            SESSION,
        ),
        Envelope.new(
            "sensor/reading",
            "demo_pub",
            {"device_id": "esp32-1", "temperature_c": 182.5, "current_a": 1.2},
            SESSION,
        ),
    ]


def print_message(msg: Envelope) -> None:
    latency_ms = (time.time() - msg.ts) * 1000
    print(f"[{msg.type}] from={msg.source} latency={latency_ms:.1f}ms payload={msg.payload}")


def selftest(bus_url: str) -> int:
    bus = connect(bus_url, client_id="demo_selftest")
    received: list[Envelope] = []
    done = threading.Event()
    expected = len(fake_messages())

    def on_message(msg: Envelope) -> None:
        print_message(msg)
        received.append(msg)
        if len(received) == expected:
            done.set()

    bus.subscribe("#", on_message)
    time.sleep(0.3)  # MQTT 구독이 브로커에 등록될 시간
    for msg in fake_messages():
        bus.publish(msg)
    ok = done.wait(timeout=5)
    bus.close()
    print(f"{'OK' if ok else 'FAIL'}: {len(received)}/{expected}건 수신 ({bus_url})")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=["selftest", "pub", "sub"])
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수")
    args = parser.parse_args()

    if args.mode == "selftest":
        return selftest(args.bus or "memory://")
    bus = connect(args.bus, client_id=f"demo_{args.mode}")
    if args.mode == "pub":
        for msg in fake_messages():
            bus.publish(msg)
            print(f"sent {msg.type}")
        bus.close()
        return 0
    bus.subscribe("#", print_message)
    print("구독 중... (Ctrl+C로 종료)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
