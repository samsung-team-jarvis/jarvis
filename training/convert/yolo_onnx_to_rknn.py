"""YOLOv8 ONNX → RKNN 변환.

ONNX는 airockchip/ultralytics_yolov8 포크로 export한 것이어야 한다 (recipes/yolo-to-rknn.md).
실행 환경: Linux x86_64 또는 Linux aarch64 + rknn-toolkit2 (macOS 불가).

사용:
    python training/convert/yolo_onnx_to_rknn.py --onnx best.onnx --dataset dataset.txt \
        --out best_int8.rknn --dtype i8

dataset.txt: 캘리브레이션 이미지 경로를 한 줄에 하나씩 (Train 세트에서만).
"""

import argparse
import pathlib
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--onnx", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--dataset", type=pathlib.Path, help="i8/u8 양자화 시 필수")
    parser.add_argument("--dtype", choices=["i8", "u8", "fp"], default="i8")
    parser.add_argument("--platform", default="rk3588")
    return parser.parse_args()


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
            (
                "build",
                lambda: rknn.build(
                    do_quantization=quantize, dataset=str(args.dataset) if quantize else None
                ),
            ),
            ("export_rknn", lambda: rknn.export_rknn(str(args.out))),
        ]
        for name, call in steps:
            if call() != 0:
                print(f"{name} 실패")
                return 1
            print(f"{name} 완료")
    finally:
        rknn.release()

    size_mb = args.out.stat().st_size / 1e6
    print(f"OK: {args.out} ({size_mb:.1f} MB, {args.dtype}, {time.monotonic() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
