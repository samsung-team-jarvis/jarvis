"""webview 실행 (UI-03): 버스 → 브라우저 시연 화면.

python -m services.webview                  # http://0.0.0.0:8090 (버스는 JARVIS_BUS, 기본 MQTT)
python -m services.webview --port 9000
"""

from __future__ import annotations

import argparse
import datetime
import signal
import sys
import threading

from common.bus import connect
from services.webview.server import Server
from services.webview.service import Feed, device_label


def main() -> int:
    parser = argparse.ArgumentParser(description="보드에서 일어나는 일을 브라우저로 보여 준다")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--host", default="0.0.0.0", help="0.0.0.0이면 같은 공유기의 PC에서 접속")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--session", default=None, help="heartbeat session_id (생략 시 s_<시각>)")
    args = parser.parse_args()

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="webview")
    feed = Feed(bus, session_id, device=device_label())
    feed.start()
    server = Server((args.host, args.port), feed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"webview 시작: http://{args.host}:{server.server_port} (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.5):
            feed.heartbeat()
    except KeyboardInterrupt:
        pass
    server.stop()
    bus.close()
    print(f"OK: 턴 {feed.turns}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
