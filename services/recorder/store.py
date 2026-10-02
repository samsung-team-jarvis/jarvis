"""세션별 JSONL 녹화 파일 쓰기·읽기.

한 줄 = 봉투(Envelope) JSON 하나. 파일 이름은 `<session_id>.jsonl`.
쓰는 즉시 flush해서 프로세스가 갑자기 죽어도 그때까지의 메시지는 남는다.
"""

from __future__ import annotations

import collections
import pathlib
import re
import threading
from collections.abc import Iterator

from common.messages import Envelope, MessageError

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def session_filename(session_id: str) -> str:
    """session_id를 파일 이름으로 안전하게 바꾼다 (경로 구분자 등 제거)."""
    safe = _UNSAFE.sub("_", session_id).strip("._") or "unknown"
    return f"{safe}.jsonl"


class SessionWriter:
    """세션마다 파일을 열어 두고 메시지를 한 줄씩 덧붙인다. 여러 스레드에서 불러도 안전하다."""

    def __init__(self, out_dir: str | pathlib.Path) -> None:
        self.out_dir = pathlib.Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._files: dict[str, object] = {}
        self._lock = threading.Lock()
        self.counts: collections.Counter[tuple[str, str]] = collections.Counter()

    def path_for(self, session_id: str) -> pathlib.Path:
        return self.out_dir / session_filename(session_id)

    def write(self, msg: Envelope) -> None:
        line = msg.to_json() + "\n"
        with self._lock:
            f = self._files.get(msg.session_id)
            if f is None:
                f = self.path_for(msg.session_id).open("a", encoding="utf-8")
                self._files[msg.session_id] = f
            f.write(line)
            f.flush()
            self.counts[(msg.session_id, msg.type)] += 1

    def close(self) -> None:
        with self._lock:
            for f in self._files.values():
                f.close()
            self._files.clear()


def read_session(path: str | pathlib.Path, strict: bool = False) -> Iterator[Envelope]:
    """녹화 파일을 봉투로 읽는다. strict=False면 깨진 줄(쓰다 끊긴 마지막 줄 등)은 건너뛴다."""
    with pathlib.Path(path).open(encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                yield Envelope.from_json(line)
            except MessageError as exc:
                if strict:
                    raise MessageError(f"{path}:{lineno}: {exc}") from exc
                continue


def summarize(path: str | pathlib.Path) -> dict:
    """토픽별 개수, 첫·마지막 메시지 시각(ts), 길이(초), 출처 목록."""
    counts: collections.Counter[str] = collections.Counter()
    sources: set[str] = set()
    first = last = None
    session_ids: set[str] = set()
    for msg in read_session(path):
        counts[msg.type] += 1
        sources.add(msg.source)
        session_ids.add(msg.session_id)
        first = msg.ts if first is None else min(first, msg.ts)
        last = msg.ts if last is None else max(last, msg.ts)
    return {
        "file": str(path),
        "sessions": sorted(session_ids),
        "messages": sum(counts.values()),
        "by_topic": dict(sorted(counts.items())),
        "sources": sorted(sources),
        "duration_s": round(last - first, 3) if first is not None else 0.0,
    }
