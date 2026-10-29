"""추론 엔진: 입력 텐서(1×3×640×640) → 모델 출력 9개. 노트북은 onnxruntime(CPU), 보드는 RKNN(예정).

보드 엔진(rknn-toolkit-lite2, NPU)은 보드를 받으면 같은 자리에 붙인다 — 후처리(detect.py)는 그대로.
"""

from __future__ import annotations

import numpy as np

THREADS = 2  # 노트북 시연에서 STT·LLM과 CPU를 나눠 쓴다


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

    def __call__(self, tensor: np.ndarray) -> list[np.ndarray]:
        return self.session.run(None, {self.input: tensor})
