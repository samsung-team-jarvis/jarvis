"""webview HTTP: 화면 페이지 · /view.json · /events (Server-Sent Events).

SSE는 브라우저가 연결을 열어 두면 서버가 줄 단위로 계속 보내는 방식이다. 바뀔 때 바로,
바뀐 게 없어도 1초마다 지금 정보를 보낸다 (응답 시간·서비스 생존 표시를 갱신).
파이썬 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from services.webview.service import Feed

PAGE = pathlib.Path(__file__).with_name("static") / "index.html"
PUSH_S = 1.0


def _json(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], feed: Feed) -> None:
        self.feed = feed
        self.stopping = threading.Event()
        super().__init__(address, Handler)

    def stop(self) -> None:
        self.stopping.set()
        with self.feed.changed:
            self.feed.changed.notify_all()  # 기다리는 /events 연결을 깨운다
        self.shutdown()
        self.server_close()


class Handler(BaseHTTPRequestHandler):
    server: Server

    def do_GET(self) -> None:  # noqa: N802 (http.server 규칙)
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif path == "/view.json":
            self._send(200, "application/json; charset=utf-8", _json(self.server.feed.snapshot()))
        elif path == "/events":
            self._events()
        else:
            self._send(404, "text/plain; charset=utf-8", "없는 주소".encode())

    def _send(self, code: int, kind: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _events(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        feed, version = self.server.feed, -1
        try:
            while not self.server.stopping.is_set():
                view = feed.snapshot()
                version = view["version"]
                self.wfile.write(b"data: " + _json(view) + b"\n\n")
                self.wfile.flush()
                feed.wait(version, PUSH_S)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 브라우저가 닫힘

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # 요청마다 찍지 않는다 (launch.py 로그가 묻힌다)
