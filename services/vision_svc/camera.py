"""화면 입력이 끊겼을 때 알리고, 카메라면 다시 연다 (VIS-12).

화면이 끊기면 `fusion_svc`는 사람이 없는 것으로 본다 (interfaces §2.3 근거 만료) → 30초 뒤
방치 경고, 60초 뒤 자동 차단(FUS-09). 그래서 끊긴 것을 로그로 남겨, 불이 꺼진 이유를 알 수
있게 한다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

GAP_S = 1.0  # 이만큼 화면이 없으면 끊긴 것 (fusion_svc의 화면 만료는 2초)
REOPEN_S = 2.0  # 카메라를 다시 열어 보는 간격


class GapWatch:
    """화면이 GAP_S 넘게 없으면 한 번 경고하고, 다시 들어오면 한 번 알린다."""

    def __init__(self, what: str, clock: Callable[[], float] = time.monotonic) -> None:
        self.what = what
        self.clock = clock
        self.last: float | None = None  # 마지막으로 화면을 받은 시각
        self.since = clock()  # 화면을 기다리기 시작한 시각 (받은 적 없을 때)
        self.gap = False
        self.gaps = 0  # 끊긴 횟수

    def frame(self) -> None:
        now = self.clock()
        if self.gap:
            log.warning("%s 다시 들어옴 (%.1f초 끊김)", self.what, now - (self.last or self.since))
            self.gap = False
        self.last = now

    def check(self) -> bool:
        """지금 끊긴 상태인가. 끊긴 순간에 한 번 경고한다."""
        waited = self.clock() - (self.last if self.last is not None else self.since)
        if waited > GAP_S and not self.gap:
            self.gap = True
            self.gaps += 1
            log.warning(
                "%s %.1f초째 없음 — 상황 인식은 사람이 없는 것으로 본다 (60초 뒤 자동 차단)",
                self.what,
                waited,
            )
        return self.gap


class Camera:
    """`cv2.VideoCapture` 감싸기. 읽기가 GAP_S 넘게 실패하면 REOPEN_S마다 다시 연다."""

    def __init__(
        self,
        index: int,
        open_fn: Callable[[int], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if open_fn is None:
            import cv2

            open_fn = cv2.VideoCapture
        self.index = index
        self.open_fn = open_fn
        self.clock = clock
        self.watch = GapWatch(f"카메라 {index} 화면", clock)
        self.cap = open_fn(index)
        self.opened_at = clock()
        self.reopens = 0

    def is_opened(self) -> bool:
        return bool(self.cap is not None and self.cap.isOpened())

    def read(self) -> np.ndarray | None:
        ok, frame = self.cap.read() if self.is_opened() else (False, None)
        if ok:
            self.watch.frame()
            return frame
        if self.watch.check() and self.clock() - self.opened_at >= REOPEN_S:
            self._reopen()
        return None

    def _reopen(self) -> None:
        if self.cap is not None:
            self.cap.release()
        self.cap = self.open_fn(self.index)
        self.opened_at = self.clock()
        self.reopens += 1
        log.warning("카메라 %d 다시 열기 %s", self.index, "성공" if self.is_opened() else "실패")

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
