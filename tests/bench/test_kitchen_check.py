import pytest

from bench.kitchen_check import KitchenChecker, jpeg_size, report
from common import kitchen_link as link
from common.bus import MemoryBus
from services.kitchen_gw.fake_kitchen import FakeKitchen, FrameSender

# 640×360 JPEG의 머리 부분 (SOI → APP0 → SOF0). 그림 데이터는 검사에 쓰지 않는다.
JPEG_640 = (
    b"\xff\xd8"
    + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\xff\xc0\x00\x11\x08\x01\x68\x02\x80\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    + b"\xff\xd9"
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class NoDedupKitchen(FakeKitchen):
    """같은 seq를 또 실행하는 (규격 위반) 가상 주방."""

    def on_cmd(self, topic: str, data: bytes) -> None:
        self._acks.clear()
        super().on_cmd(topic, data)


class NoWatchdogKitchen(FakeKitchen):
    """생존 신호가 끊겨도 가열 장치를 끄지 않는 (규격 위반) 가상 주방."""

    def _heartbeat_alive(self, now: float) -> bool:
        return True


def run(kitchen_cls=FakeKitchen, frames: list[bytes] | None = None, long: bool = False):
    clock, bus = FakeClock(), MemoryBus()
    kitchen = kitchen_cls(bus, clock=clock)
    sender = FrameSender(bus, frames, clock=clock) if frames else None

    def sleep(seconds: float) -> None:
        clock.now += seconds
        kitchen.tick()
        if sender:
            sender.tick()

    checker = KitchenChecker(bus, clock=clock, sleep=sleep, first_seq=1000)
    kitchen.start()
    return {r.name: r for r in checker.run(long=long, require_frames=bool(frames))}


def test_fake_kitchen_passes_everything():
    results = run(frames=[JPEG_640])
    failed = [r for r in results.values() if r.ok is False]
    assert failed == []
    assert results["인식용 화면 (HW-20)"].ok is True


def test_no_frames_is_not_applicable_unless_required():
    results = run()
    assert results["인식용 화면 (HW-20)"].ok is None
    assert all(r.ok is not False for r in results.values())


def test_long_run_checks_hard_limit():
    result = run(long=True)["265°C 자체 끄기 (HW-19, --long)"]
    assert result.ok is True, result.got


def test_catches_duplicate_seq_execution():
    results = run(NoDedupKitchen)
    assert results["같은 seq 재실행 안 함 (HW-16)"].ok is False
    assert "다시 켜짐" in results["같은 seq 재실행 안 함 (HW-16)"].got


def test_catches_missing_heartbeat_watchdog():
    results = run(NoWatchdogKitchen)
    assert results["생존 신호 끊김 → 가열 장치 OFF (HW-18)"].ok is False
    assert results["끊긴 동안 가열 장치 켜기 거절 (HW-18)"].ok is False


def test_catches_wrong_frame_size():
    small = JPEG_640.replace(b"\x01\x68\x02\x80", b"\x01\xe0\x02\x80")  # 640×480
    result = run(frames=[small])["인식용 화면 (HW-20)"]
    assert result.ok is False
    assert "640×480" in result.got


@pytest.mark.parametrize(
    ("data", "size"),
    [(JPEG_640, (640, 360)), (b"\x89PNG\r\n", None), (b"\xff\xd8\xff\xd9", None)],
)
def test_jpeg_size(data, size):
    assert jpeg_size(data) == size


def test_report_counts_only_judged_items():
    results = list(run().values())
    text = report(results)
    judged = sum(r.ok is not None for r in results)
    assert f"{judged} / {judged} 통과" in text
    assert "해당 없음" in text
    assert link.TOPIC_CMD not in text
