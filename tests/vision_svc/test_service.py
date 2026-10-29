"""vision_svc (VIS-08): 정한 클래스만 vision/objects로 발행, 프레임 번호·구간 시간을 채운다."""

import numpy as np
import pytest

from common.bus import MemoryBus
from services.vision_svc.service import VisionService
from tests.vision_svc.test_detect import outputs_with

pytest.importorskip("cv2")


def fake_engine(cls: int):
    def run(tensor):
        assert tensor.shape == (1, 3, 640, 640)
        return outputs_with(10, 20, (2, 3, 4, 5), cls, 0.9)

    return run


def test_person_is_published_with_timings() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("vision/objects", got.append)
    service = VisionService(bus, "s_vis", fake_engine(0))

    service.process(np.zeros((640, 640, 3), dtype=np.uint8))
    service.process(np.zeros((640, 640, 3), dtype=np.uint8))

    assert [m.payload["frame_id"] for m in got] == [0, 1]
    p = got[0].payload
    assert [o["cls"] for o in p["objects"]] == ["person"]
    assert p["objects"][0]["conf"] == 0.9
    assert all(p[k] >= 0 for k in ("pre_ms", "npu_ms", "post_ms"))
    assert got[0].source == "vision_svc" and got[0].session_id == "s_vis"


def test_other_classes_are_not_published() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("vision/objects", got.append)
    VisionService(bus, "s_vis", fake_engine(45)).process(np.zeros((640, 640, 3), dtype=np.uint8))
    assert got[0].payload["objects"] == []  # bowl은 기본 목록(person)에 없다


def test_unknown_class_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="모델에 없는 클래스"):
        VisionService(MemoryBus(), "s", fake_engine(0), classes=["pan"])
