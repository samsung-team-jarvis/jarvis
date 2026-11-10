"""YOLOv8 전처리·후처리 (VIS-08). numpy만 쓴다 — 노트북(onnxruntime)과 보드(RKNN)가 같이 쓴다.

모델은 rknn_model_zoo의 YOLOv8n ONNX와 같은 출력 형식이다: 크기 3개(80·40·20칸)마다
상자 분포(64 = 4변 × 16칸, DFL) · 클래스 점수(80, sigmoid 적용됨) · 점수 합(쓰지 않음) — 출력 9개.
airockchip/ultralytics_yolov8 포크로 export한 맞춤 모델도 같은 형식이다 (training/yolo).
후처리는 rknn_model_zoo examples/yolov8/python/yolov8.py와 같은 계산이다 (torch 없이).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SIZE = 640
CONF = 0.25
NMS_IOU = 0.45
# COCO 80 클래스 (사전학습 모델의 번호 순서)
COCO = (
    "person bicycle car motorbike aeroplane bus train truck boat traffic_light fire_hydrant "
    "stop_sign parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe "
    "backpack umbrella handbag tie suitcase frisbee skis snowboard sports_ball kite baseball_bat "
    "baseball_glove skateboard surfboard tennis_racket bottle wine_glass cup fork knife spoon bowl "
    "banana apple sandwich orange broccoli carrot hot_dog pizza donut cake chair sofa pottedplant "
    "bed diningtable toilet tvmonitor laptop mouse remote keyboard cell_phone microwave oven "
    "toaster sink refrigerator book clock vase scissors teddy_bear hair_drier toothbrush"
).split()


@dataclass(frozen=True)
class Letterbox:
    """원본 → 640×640으로 비율을 지켜 줄이고 남는 곳을 채운 정보 (상자를 원본 좌표로 되돌릴 때)."""

    scale: float
    pad_x: float
    pad_y: float


def preprocess(bgr: np.ndarray, size: int = SIZE) -> tuple[np.ndarray, Letterbox]:
    """BGR 이미지(H×W×3, uint8) → 입력 텐서(1×3×size×size, float32 0~1, RGB)."""
    import cv2

    h, w = bgr.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = round(w * scale), round(h * scale)
    pad_x, pad_y = (size - nw) / 2, (size - nh) / 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    top, left = int(round(pad_y - 0.1)), int(round(pad_x - 0.1))
    canvas[top : top + nh, left : left + nw] = cv2.resize(bgr, (nw, nh))
    rgb = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0
    return np.ascontiguousarray(rgb), Letterbox(scale, left, top)


def _dfl(position: np.ndarray) -> np.ndarray:
    """상자 분포(1×64×H×W) → 네 변까지의 거리(1×4×H×W, 칸 단위)."""
    n, c, h, w = position.shape
    y = position.reshape(n, 4, c // 4, h, w)
    y = np.exp(y - y.max(axis=2, keepdims=True))
    y /= y.sum(axis=2, keepdims=True)
    return (y * np.arange(c // 4, dtype=np.float32).reshape(1, 1, -1, 1, 1)).sum(axis=2)


def _boxes(position: np.ndarray, size: int) -> np.ndarray:
    grid_h, grid_w = position.shape[2:4]
    col, row = np.meshgrid(np.arange(grid_w), np.arange(grid_h))
    grid = np.stack([col, row])[None].astype(np.float32)
    stride = np.array([size // grid_w, size // grid_h], dtype=np.float32).reshape(1, 2, 1, 1)
    dist = _dfl(position)
    xyxy = np.concatenate([grid + 0.5 - dist[:, :2], grid + 0.5 + dist[:, 2:]], axis=1)
    return (xyxy * np.concatenate([stride, stride], axis=1))[0].reshape(4, -1).T


def _nms(boxes: np.ndarray, scores: np.ndarray, iou: float) -> list[int]:
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        x1 = np.maximum(boxes[i, 0], boxes[rest, 0])
        y1 = np.maximum(boxes[i, 1], boxes[rest, 1])
        x2 = np.minimum(boxes[i, 2], boxes[rest, 2])
        y2 = np.minimum(boxes[i, 3], boxes[rest, 3])
        inter = np.clip(x2 - x1, 0, None) * np.clip(y2 - y1, 0, None)
        area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        overlap = inter / (area[i] + area[rest] - inter + 1e-9)
        order = rest[overlap <= iou]
    return keep


def postprocess(
    outputs: list[np.ndarray],
    box: Letterbox,
    width: int,
    height: int,
    conf: float = CONF,
    iou: float = NMS_IOU,
    size: int = SIZE,
) -> list[dict]:
    """모델 출력 9개 → [{cls, conf, bbox: [x1, y1, x2, y2] 원본 픽셀}] (점수 높은 순)."""
    per = len(outputs) // 3
    boxes, scores = [], []
    for i in range(3):
        boxes.append(_boxes(outputs[per * i], size))
        scores.append(outputs[per * i + 1][0].reshape(outputs[per * i + 1].shape[1], -1).T)
    boxes_all, scores_all = np.concatenate(boxes), np.concatenate(scores)
    cls = scores_all.argmax(axis=1)
    best = scores_all[np.arange(len(cls)), cls]
    hit = best >= conf
    boxes_all, cls, best = boxes_all[hit], cls[hit], best[hit]
    found = []
    for c in np.unique(cls):  # 클래스마다 따로 NMS (rknn_model_zoo와 같다)
        idx = np.where(cls == c)[0]
        for k in _nms(boxes_all[idx], best[idx], iou):
            j = idx[k]
            x1, y1, x2, y2 = boxes_all[j]
            bbox = [
                float(np.clip((x1 - box.pad_x) / box.scale, 0, width)),
                float(np.clip((y1 - box.pad_y) / box.scale, 0, height)),
                float(np.clip((x2 - box.pad_x) / box.scale, 0, width)),
                float(np.clip((y2 - box.pad_y) / box.scale, 0, height)),
            ]
            found.append({"cls": COCO[int(c)], "conf": float(best[j]), "bbox": bbox})
    return sorted(found, key=lambda d: -d["conf"])
