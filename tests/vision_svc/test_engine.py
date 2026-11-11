"""엔진 고르기와 RKNN 엔진 (VIS-11). 보드가 없어도 돌도록 rknnlite를 가짜로 바꿔 끼운다."""

import sys
import types

import numpy as np
import pytest

from common.bus import MemoryBus
from services.vision_svc import detect, engine
from services.vision_svc.service import VisionService
from tests.vision_svc.test_detect import outputs_with

pytest.importorskip("cv2")


class FakeRKNNLite:
    NPU_CORE_0, NPU_CORE_1, NPU_CORE_2, NPU_CORE_0_1_2, NPU_CORE_AUTO = 1, 2, 4, 7, 0
    load_ret = init_ret = 0
    instances: list["FakeRKNNLite"] = []

    def __init__(self, verbose: bool = False) -> None:
        self.inputs: list[np.ndarray] = []
        self.core_mask = None
        self.released = False
        FakeRKNNLite.instances.append(self)

    def load_rknn(self, path: str) -> int:
        self.path = path
        return self.load_ret

    def init_runtime(self, core_mask: int = 0) -> int:
        self.core_mask = core_mask
        return self.init_ret

    def inference(self, inputs: list[np.ndarray]):
        self.inputs.append(inputs[0])
        return outputs_with(10, 20, (2, 3, 4, 5), 0, 0.9)

    def release(self) -> None:
        self.released = True


@pytest.fixture
def rknnlite(monkeypatch):
    FakeRKNNLite.instances = []
    FakeRKNNLite.load_ret = FakeRKNNLite.init_ret = 0
    api = types.ModuleType("rknnlite.api")
    api.RKNNLite = FakeRKNNLite
    monkeypatch.setitem(sys.modules, "rknnlite", types.ModuleType("rknnlite"))
    monkeypatch.setitem(sys.modules, "rknnlite.api", api)
    return FakeRKNNLite


def test_rknn_model_runs_on_npu_core0_with_uint8_nhwc_input(rknnlite) -> None:
    eng = engine.load("models/x.rknn")
    rt = rknnlite.instances[0]
    assert isinstance(eng, engine.RknnEngine) and rt.path == "models/x.rknn"
    assert rt.core_mask == FakeRKNNLite.NPU_CORE_0 and eng.name == "RKNN NPU core 0"

    bus, got = MemoryBus(), []
    bus.subscribe("vision/objects", got.append)
    VisionService(bus, "s", eng).process(np.zeros((360, 640, 3), dtype=np.uint8))

    x = rt.inputs[0]  # 변환 때 정규화를 모델에 넣었으니 0~255 그대로, 채널이 마지막
    assert x.shape == (1, 640, 640, 3) and x.dtype == np.uint8
    assert x[0, 0, 0].tolist() == [114, 114, 114]  # 위쪽 여백
    assert [o["cls"] for o in got[0].payload["objects"]] == ["person"]
    eng.release()
    assert rt.released


def test_npu_core_can_be_chosen(rknnlite) -> None:
    engine.load("m.RKNN", core="all")
    assert rknnlite.instances[0].core_mask == FakeRKNNLite.NPU_CORE_0_1_2
    with pytest.raises(ValueError, match="NPU 코어"):
        engine.load("m.rknn", core="3")


def test_npu_failures_are_reported(rknnlite) -> None:
    rknnlite.load_ret = -1
    with pytest.raises(RuntimeError, match="읽지 못했습니다"):
        engine.load("m.rknn")
    rknnlite.load_ret, rknnlite.init_ret = 0, -1
    with pytest.raises(RuntimeError, match="NPU 런타임"):
        engine.load("m.rknn")


def test_rknn_without_runtime_says_board_only(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "rknnlite", None)  # import 실패
    with pytest.raises(RuntimeError, match="보드 전용"):
        engine.load("m.rknn")


def test_onnx_input_is_float_nchw_and_same_as_preprocess() -> None:
    img = np.random.default_rng(0).integers(0, 256, (360, 640, 3), dtype=np.uint8)
    rgb, box = detect.letterbox(img)
    tensor, box2 = detect.preprocess(img)
    assert box == box2
    np.testing.assert_array_equal(engine.OnnxEngine.prepare(None, rgb), tensor)
    assert rgb.shape == (640, 640, 3) and rgb.dtype == np.uint8
    # RGB: 원본 BGR의 채널 순서가 뒤집힌다
    np.testing.assert_array_equal(rgb[140 + 5, 7], img[5, 7, ::-1])


def test_non_float_npu_output_stops_instead_of_wrong_boxes(rknnlite, monkeypatch) -> None:
    eng = engine.load("m.rknn")
    raw = [o.astype(np.int8) for o in outputs_with(10, 20, (2, 3, 4, 5), 0, 0.9)]
    monkeypatch.setattr(rknnlite.instances[0], "inference", lambda inputs: raw)
    with pytest.raises(RuntimeError, match="float가 아닙니다"):
        eng(np.zeros((1, 640, 640, 3), np.uint8))
