"""추론 엔진: 전처리한 화면 → 모델 출력 9개. 노트북은 onnxruntime(CPU), 보드는 RKNN(NPU).

엔진마다 받는 입력이 달라 `prepare()`가 맞춰 준다 (서비스는 이것까지 전처리 시간으로 잰다):

| 엔진 | 모델 | 입력 |
|---|---|---|
| `OnnxEngine` | `.onnx` | 1×3×640×640 float32 0~1 (`detect.to_tensor`) |
| `RknnEngine` | `.rknn` | 1×640×640×3 uint8 RGB — 변환 때 mean 0 · std 255를 모델 안에 넣었다 |

후처리(detect.py)는 두 엔진이 같다 (rknn_model_zoo yolov8 예제와 같은 출력 형식).
"""

from __future__ import annotations

import pathlib

import numpy as np

from services.vision_svc import detect

THREADS = 2  # 노트북 시연에서 STT·LLM과 CPU를 나눠 쓴다
# RK3588 NPU 코어 3개. YOLO는 core0 (architecture overview). LLM은 CPU(llama.cpp)라 겹치지 않는다
NPU_CORES = {
    "0": "NPU_CORE_0",
    "1": "NPU_CORE_1",
    "2": "NPU_CORE_2",
    "all": "NPU_CORE_0_1_2",
    "auto": "NPU_CORE_AUTO",
}
NPU_CORE = "0"


class OnnxEngine:
    name = "onnxruntime CPU"

    def __init__(self, model_path: str, threads: int = THREADS) -> None:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        self.input = self.session.get_inputs()[0].name

    def prepare(self, rgb: np.ndarray) -> np.ndarray:
        return detect.to_tensor(rgb)

    def __call__(self, tensor: np.ndarray) -> list[np.ndarray]:
        return self.session.run(None, {self.input: tensor})


class RknnEngine:
    """rknn-toolkit-lite2 (보드 aarch64). 설치: recipes/board-setup.md §4."""

    def __init__(self, model_path: str, core: str = NPU_CORE) -> None:
        if core not in NPU_CORES:
            raise ValueError(f"NPU 코어는 {sorted(NPU_CORES)} 중 하나: {core!r}")
        try:
            from rknnlite.api import RKNNLite
        except ImportError as exc:
            raise RuntimeError(
                "rknn-toolkit-lite2가 없습니다 (보드 전용). 노트북에서는 .onnx 모델을 쓰세요"
            ) from exc
        self.rknn = RKNNLite(verbose=False)
        if self.rknn.load_rknn(model_path) != 0:
            raise RuntimeError(f"RKNN 모델을 읽지 못했습니다: {model_path}")
        if self.rknn.init_runtime(core_mask=getattr(RKNNLite, NPU_CORES[core])) != 0:
            raise RuntimeError("NPU 런타임을 시작하지 못했습니다 (librknnrt.so·드라이버 확인)")
        self.name = f"RKNN NPU core {core}"

    def prepare(self, rgb: np.ndarray) -> np.ndarray:
        return rgb[None]

    def __call__(self, image: np.ndarray) -> list[np.ndarray]:
        outputs = self.rknn.inference(inputs=[image])
        if outputs is None:
            raise RuntimeError("NPU 추론 실패")
        # 변환할 때 출력 형식이 int8로 바뀐다는 경고가 나온다. Python API는 float로 돌려준다고 보고
        # (rknn_model_zoo 예제와 같은 쓰임), 아니면 후처리가 틀리므로 멈춘다 (보드에서 확인 필요)
        if not np.issubdtype(outputs[0].dtype, np.floating):
            raise RuntimeError(f"NPU 출력이 float가 아닙니다 ({outputs[0].dtype}) — 후처리 불가")
        return outputs

    def release(self) -> None:
        self.rknn.release()


def load(model_path: str, threads: int = THREADS, core: str = NPU_CORE) -> OnnxEngine | RknnEngine:
    """모델 확장자로 엔진을 고른다: `.rknn` → NPU, 나머지(`.onnx`) → CPU."""
    if pathlib.Path(model_path).suffix.lower() == ".rknn":
        return RknnEngine(model_path, core=core)
    return OnnxEngine(model_path, threads=threads)
