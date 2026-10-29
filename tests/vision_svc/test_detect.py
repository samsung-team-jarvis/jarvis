"""YOLOv8 전처리·후처리 (VIS-08): 모델 없이 출력 텐서를 만들어 상자 계산을 확인한다."""

import numpy as np
import pytest

from services.vision_svc import detect

pytest.importorskip("cv2")


def outputs_with(cell_row: int, cell_col: int, dist: tuple[int, int, int, int], cls: int, score):
    """80칸 크기(stride 8)의 한 칸에만 물체가 있는 모델 출력 9개."""
    outs = []
    for n in (80, 40, 20):
        box = np.full((1, 64, n, n), -20.0, dtype=np.float32)
        conf = np.zeros((1, 80, n, n), dtype=np.float32)
        if n == 80:
            for side, d in enumerate(dist):  # 네 변 분포를 d칸에 몰아 둔다
                box[0, side * 16 + d, cell_row, cell_col] = 20.0
            conf[0, cls, cell_row, cell_col] = score
        outs += [box, conf, conf.sum(axis=1, keepdims=True)]
    return outs


def test_box_comes_from_the_grid_cell_and_distances() -> None:
    lb = detect.Letterbox(scale=1.0, pad_x=0, pad_y=0)
    found = detect.postprocess(outputs_with(10, 20, (2, 3, 4, 5), 0, 0.9), lb, 640, 640)
    assert len(found) == 1 and found[0]["cls"] == "person"
    assert found[0]["conf"] == pytest.approx(0.9)
    # (칸 + 0.5 ∓ 거리) × 8
    assert found[0]["bbox"] == pytest.approx(
        [(20.5 - 2) * 8, (10.5 - 3) * 8, (20.5 + 4) * 8, (10.5 + 5) * 8]
    )


def test_below_threshold_is_dropped_and_letterbox_is_undone() -> None:
    assert (
        detect.postprocess(
            outputs_with(10, 20, (2, 3, 4, 5), 0, 0.2), detect.Letterbox(1, 0, 0), 640, 640
        )
        == []
    )
    lb = detect.Letterbox(scale=0.5, pad_x=0, pad_y=140)  # 1280×720 → 640×360 + 위아래 140
    [d] = detect.postprocess(outputs_with(30, 20, (2, 2, 2, 2), 0, 0.9), lb, 1280, 720)
    assert d["bbox"] == pytest.approx(
        [(18.5 * 8) / 0.5, (28.5 * 8 - 140) / 0.5, (22.5 * 8) / 0.5, (32.5 * 8 - 140) / 0.5]
    )


def test_overlapping_boxes_of_one_class_are_merged() -> None:
    a = outputs_with(10, 20, (2, 3, 4, 5), 0, 0.9)
    b = outputs_with(10, 21, (3, 3, 3, 5), 0, 0.8)  # 옆 칸, 거의 같은 상자
    pairs = enumerate(zip(a, b, strict=True))
    merged = [x + y if i % 3 else np.maximum(x, y) for i, (x, y) in pairs]
    found = detect.postprocess(merged, detect.Letterbox(1, 0, 0), 640, 640)
    assert [d["conf"] for d in found] == pytest.approx([0.9])


def test_preprocess_keeps_aspect_ratio_with_gray_padding() -> None:
    img = np.zeros((360, 640, 3), dtype=np.uint8)
    tensor, lb = detect.preprocess(img)
    assert tensor.shape == (1, 3, 640, 640) and tensor.dtype == np.float32
    assert (lb.scale, lb.pad_x, lb.pad_y) == (1.0, 0, 140)
    assert tensor[0, :, 0, 0] == pytest.approx([114 / 255] * 3)  # 위쪽 여백
    assert tensor[0, :, 320, 320] == pytest.approx([0, 0, 0])  # 원본 자리
