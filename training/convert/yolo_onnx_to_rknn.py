"""YOLOv8 ONNX → RKNN 변환.

ONNX는 airockchip/ultralytics_yolov8 포크로 export한 것이어야 한다 (recipes/yolo-to-rknn.md).
실행 환경: Linux x86_64 또는 Linux aarch64 + rknn-toolkit2 (macOS 불가).

사용:
    python training/convert/yolo_onnx_to_rknn.py --onnx best.onnx --dataset dataset.txt \
        --out best_int8.rknn --dtype i8

dataset.txt: 캘리브레이션 이미지 경로를 한 줄에 하나씩 (Train 세트에서만).
상대 경로는 dataset.txt가 있는 폴더 기준으로 해석한다 (make_calib_list.py --copy 결과).

--check 사진...: 변환한 모델을 rknn-toolkit2 시뮬레이터로 돌려, 같은 사진에서 ONNX(onnxruntime)와
결과를 비교한다 (물체 수·같은 물체의 점수 차·상자 겹침). 전처리·후처리는 vision_svc와 같은 코드다.
캘리브레이션에 쓰지 않은 사진으로 확인한다. 시뮬레이터는 보드 NPU와 같은 INT8 계산을 흉내 낼 뿐이라
속도는 보드에서 잰다. 시뮬레이터는 진짜 x86 CPU가 필요하다 (M1 Mac의 amd64 에뮬레이션에서는
"Illegal instruction"으로 죽는다 — export까지는 끝난다).
"""

import argparse
import json
import os
import pathlib
import sys
import time

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MATCH_IOU = 0.5  # 이만큼 겹치면 ONNX와 RKNN이 같은 물체를 찾은 것으로 본다


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--onnx", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--dataset", type=pathlib.Path, help="i8/u8 양자화 시 필수")
    parser.add_argument("--dtype", choices=["i8", "u8", "fp"], default="i8")
    parser.add_argument("--platform", default="rk3588")
    parser.add_argument(
        "--check", nargs="*", type=pathlib.Path, default=[], help="ONNX와 결과를 비교할 사진"
    )
    parser.add_argument("--report", type=pathlib.Path, help="비교 결과를 JSON으로 저장")
    return parser.parse_args()


def _iou(a: list[float], b: list[float]) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(ref: list[dict], got: list[dict]) -> list[tuple[dict, dict, float]]:
    """같은 클래스끼리 상자가 가장 많이 겹치는 것을 짝짓는다 (점수 높은 ref부터, 한 번씩만)."""
    pairs, used = [], set()
    for r in ref:
        best, best_iou = None, MATCH_IOU
        for i, g in enumerate(got):
            if i in used or g["cls"] != r["cls"]:
                continue
            iou = _iou(r["bbox"], g["bbox"])
            if iou >= best_iou:
                best, best_iou = i, iou
        if best is not None:
            used.add(best)
            pairs.append((r, got[best], best_iou))
    return pairs


def compare(rknn: object, onnx_path: pathlib.Path, images: list[pathlib.Path]) -> dict:
    """시뮬레이터(INT8) vs onnxruntime(FP32): 사진마다 물체 수와 짝지은 물체의 차이."""
    import cv2
    import onnxruntime as ort

    sys.path.insert(0, str(REPO_ROOT))
    from services.vision_svc import detect

    if rknn.init_runtime() != 0:  # target 없이 = 시뮬레이터
        raise RuntimeError("시뮬레이터 init_runtime 실패")
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name
    rows = []
    for path in images:
        bgr = cv2.imread(str(path))
        if bgr is None:
            raise FileNotFoundError(path)
        h, w = bgr.shape[:2]
        rgb, box = detect.letterbox(bgr)
        ref = detect.postprocess(session.run(None, {name: detect.to_tensor(rgb)}), box, w, h)
        got = detect.postprocess(rknn.inference(inputs=[rgb[None]]), box, w, h)
        pairs = match(ref, got)
        diffs = [abs(r["conf"] - g["conf"]) for r, g, _ in pairs]
        row = {
            "image": path.name,
            "onnx": len(ref),
            "rknn": len(got),
            "matched": len(pairs),
            "onnx_person": sum(d["cls"] == "person" for d in ref),
            "rknn_person": sum(d["cls"] == "person" for d in got),
            "conf_diff_max": round(max(diffs, default=0.0), 3),
            "iou_min": round(min((iou for *_, iou in pairs), default=1.0), 3),
        }
        rows.append(row)
        print(
            f"{row['image']}: 물체 ONNX {row['onnx']} · RKNN {row['rknn']} · 짝 {row['matched']} "
            f"(사람 {row['onnx_person']} · {row['rknn_person']}), "
            f"점수 차 최대 {row['conf_diff_max']}, 상자 겹침 최소 {row['iou_min']}"
        )
    keys = ("onnx", "rknn", "matched", "onnx_person", "rknn_person")
    total = {k: sum(r[k] for r in rows) for k in keys}
    print(
        f"합계: 물체 ONNX {total['onnx']} · RKNN {total['rknn']} · 짝 {total['matched']}, "
        f"사람 ONNX {total['onnx_person']} · RKNN {total['rknn_person']}"
    )
    return {"images": rows, "total": total}


def build(rknn: object, dataset: pathlib.Path | None) -> int:
    """dataset.txt 안의 상대 경로가 txt 파일 위치 기준으로 풀리도록 그 폴더에서 build한다."""
    if dataset is None:
        return rknn.build(do_quantization=False)
    dataset = dataset.resolve()
    previous = os.getcwd()
    os.chdir(dataset.parent)
    try:
        return rknn.build(do_quantization=True, dataset=str(dataset))
    finally:
        os.chdir(previous)


def main() -> int:
    args = parse_args()
    quantize = args.dtype in ("i8", "u8")
    if quantize and (args.dataset is None or not args.dataset.exists()):
        print("양자화(i8/u8)에는 --dataset 파일이 필요합니다.")
        return 1

    from rknn.api import RKNN  # rknn-toolkit2가 설치된 Linux에서만 import 가능

    rknn = RKNN(verbose=False)
    started = time.monotonic()
    try:
        rknn.config(
            mean_values=[[0, 0, 0]],
            std_values=[[255, 255, 255]],
            target_platform=args.platform,
        )
        steps = [
            ("load_onnx", lambda: rknn.load_onnx(model=str(args.onnx))),
            ("build", lambda: build(rknn, args.dataset if quantize else None)),
            ("export_rknn", lambda: rknn.export_rknn(str(args.out))),
        ]
        for name, call in steps:
            if call() != 0:
                print(f"{name} 실패")
                return 1
            print(f"{name} 완료")
        if args.check:
            report = compare(rknn, args.onnx, args.check)
            report.update(onnx=args.onnx.name, rknn=args.out.name, dtype=args.dtype)
            if args.report:
                args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    finally:
        rknn.release()

    size_mb = args.out.stat().st_size / 1e6
    print(f"OK: {args.out} ({size_mb:.1f} MB, {args.dtype}, {time.monotonic() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
