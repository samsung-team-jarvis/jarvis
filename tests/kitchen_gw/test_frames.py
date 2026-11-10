"""가짜 가상 주방의 인식용 화면 (#126): 이미지를 차례로 1초에 4장 kitchen/frame으로."""

import pathlib

import pytest

from common import kitchen_link as link
from common.bus import MemoryBus
from services.kitchen_gw.fake_kitchen import FrameSender, load_frames


def test_frames_are_sent_in_turn_four_per_second() -> None:
    bus, got, now = MemoryBus(), [], [0.0]
    bus.subscribe_raw(link.TOPIC_FRAME, lambda topic, data: got.append(data))
    sender = FrameSender(bus, [b"a", b"b"], clock=lambda: now[0])
    for _ in range(21):  # 0.05초마다 1초 동안
        sender.tick()
        now[0] += 0.05
    assert got == [b"a", b"b", b"a", b"b", b"a"]  # 0 · 0.25 · 0.5 · 0.75 · 1.0초


def test_load_frames_reads_jpegs_from_a_folder_in_name_order(tmp_path: pathlib.Path) -> None:
    (tmp_path / "2.jpg").write_bytes(b"two")
    (tmp_path / "1.jpeg").write_bytes(b"one")
    (tmp_path / "note.txt").write_text("x")
    assert load_frames(tmp_path) == [b"one", b"two"]
    assert load_frames(tmp_path / "2.jpg") == [b"two"]


def test_no_frames_is_an_error() -> None:
    with pytest.raises(ValueError):
        FrameSender(MemoryBus(), [])
