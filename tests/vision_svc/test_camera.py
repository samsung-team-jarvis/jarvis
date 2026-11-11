"""카메라 끊김 감지·다시 열기 (VIS-12). 가짜 카메라·가짜 시계."""

import logging

import numpy as np

from services.vision_svc.camera import GAP_S, REOPEN_S, Camera, GapWatch


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class FakeCap:
    """plan: 읽을 때마다 True(화면)/False(실패). 비면 계속 실패."""

    def __init__(self, plan: list[bool], opens: bool = True) -> None:
        self.plan, self.opens, self.released = list(plan), opens, False

    def isOpened(self) -> bool:  # noqa: N802 (cv2 이름 그대로)
        return self.opens and not self.released

    def read(self):
        ok = self.plan.pop(0) if self.plan else False
        return ok, (np.zeros((2, 2, 3), np.uint8) if ok else None)

    def release(self) -> None:
        self.released = True


def test_unplugged_camera_warns_reopens_and_recovers(caplog) -> None:
    clock = Clock()
    caps = [FakeCap([True, True]), FakeCap([], opens=False), FakeCap([True] * 100)]
    cam = Camera(0, open_fn=lambda i: caps.pop(0), clock=clock)
    got = []
    with caplog.at_level(logging.WARNING):
        for _ in range(40):  # 0.25초마다 (4 fps) 10초
            got.append(cam.read() is not None)
            clock.t += 0.25
    assert got[:2] == [True, True]  # 처음엔 읽힘
    assert cam.reopens == 2  # 첫 다시 열기는 실패(장치 없음), 다음에 성공
    assert got[-1] is True  # 돌아옴
    assert cam.watch.gaps == 1
    text = caplog.text
    assert "없음" in text and "다시 열기 실패" in text and "다시 열기 성공" in text
    assert "다시 들어옴" in text


def test_short_hiccup_does_not_reopen() -> None:
    clock = Clock()
    cam = Camera(0, open_fn=lambda i: FakeCap([True, False, False, True] * 3), clock=clock)
    for _ in range(12):
        cam.read()
        clock.t += 0.25  # 0.5초 끊김은 GAP_S(1초) 안
    assert cam.reopens == 0 and cam.watch.gaps == 0


def test_reopen_waits_between_tries() -> None:
    clock = Clock()
    opened = []

    def open_fn(i):
        opened.append(clock.t)
        return FakeCap([], opens=False)

    cam = Camera(0, open_fn=open_fn, clock=clock)
    for _ in range(40):
        cam.read()
        clock.t += 0.25
    gaps = np.diff(opened)
    assert len(opened) >= 3 and (gaps >= REOPEN_S - 1e-9).all()  # 2초마다만 다시 연다


def test_gap_watch_warns_once_per_gap(caplog) -> None:
    clock = Clock()
    w = GapWatch("가상 주방 화면", clock)
    with caplog.at_level(logging.WARNING):
        w.frame()
        clock.t = GAP_S + 0.5
        assert w.check() and w.check()  # 한 번만 경고
        w.frame()
        clock.t += 0.2
        assert not w.check()
    assert caplog.text.count("없음") == 1 and caplog.text.count("다시 들어옴") == 1
