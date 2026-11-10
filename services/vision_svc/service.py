"""vision_svc: 화면(BGR) → YOLOv8 → `vision/objects` 발행 (interfaces §2).

정한 클래스만 발행한다 (기본 `person` — 방치 판단에 필요한 것은 "조리 구역에 사람이 있는가"다).
사전학습(COCO) 모델의 클래스 이름을 그대로 쓴다. 맞춤 학습 모델은 클래스 목록만 바꿔 넣는다.
`session_id`는 이 서비스의 것이다 (화면은 발화에서 온 메시지가 아니다).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np

from common.bus import Bus
from common.messages import Envelope
from services.vision_svc import detect

SOURCE = "vision_svc"
DEFAULT_CLASSES = ("person",)

Engine = Callable[[np.ndarray], list[np.ndarray]]


class VisionService:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        engine: Engine,
        classes: Iterable[str] = DEFAULT_CLASSES,
        conf: float = detect.CONF,
        on_objects: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        unknown = set(classes) - set(detect.COCO)
        if unknown:
            raise ValueError(f"모델에 없는 클래스: {sorted(unknown)}")
        self.bus = bus
        self.session_id = session_id
        self.engine = engine
        self.classes = frozenset(classes)
        self.conf = conf
        self.on_objects = on_objects
        self.clock = clock
        self.frame_id = 0
        self._last_heartbeat: float | None = None

    def process(self, bgr: np.ndarray) -> dict[str, Any]:
        """화면 한 장을 인식해 발행하고 payload를 돌려준다."""
        t0 = time.perf_counter()
        tensor, box = detect.preprocess(bgr)
        t1 = time.perf_counter()
        outputs = self.engine(tensor)
        t2 = time.perf_counter()
        found = detect.postprocess(outputs, box, bgr.shape[1], bgr.shape[0], conf=self.conf)
        objects = [
            {"cls": d["cls"], "conf": round(d["conf"], 3), "bbox": [round(v, 1) for v in d["bbox"]]}
            for d in found
            if d["cls"] in self.classes
        ]
        t3 = time.perf_counter()
        payload = {
            "objects": objects,
            "frame_id": self.frame_id,
            "pre_ms": round((t1 - t0) * 1000, 2),
            "npu_ms": round(
                (t2 - t1) * 1000, 2
            ),  # 노트북에서는 CPU 추론 시간 (필드 이름은 규격 그대로)
            "post_ms": round((t3 - t2) * 1000, 2),
        }
        msg = Envelope.new("vision/objects", SOURCE, payload, self.session_id)
        self.bus.publish(msg)
        self.frame_id += 1
        if self.on_objects:
            self.on_objects(msg)
        return payload

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
