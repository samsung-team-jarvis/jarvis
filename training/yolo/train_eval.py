"""YOLOv8 학습 → Test 세트 평가 → metrics.json 저장.

사용:
    python training/yolo/train_eval.py --data data.yaml --epochs 100 --out runs/kitchen_v1

- data.yaml은 Roboflow "YOLOv8" export 형식 (train / val / test 경로, names).
- 평가는 data.yaml에 test가 있으면 test, 없으면 val로 한다. Test 세트는 학습·튜닝에 쓰지 않는다.
- metrics.json 값은 docs/METRICS.md 측정 로그에 그대로 옮긴다 (측정 위치: 학습 환경, 보드 아님).
"""

import argparse
import datetime
import json
import pathlib
import sys

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", required=True, type=pathlib.Path)
    parser.add_argument("--model", default="yolov8n.pt", help="시작 가중치 (기본: COCO 사전학습)")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="예: 0 (GPU), cpu, mps. 생략 시 자동")
    parser.add_argument("--out", required=True, type=pathlib.Path, help="결과 폴더")
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    import torch
    import ultralytics
    from ultralytics import YOLO

    data_cfg = yaml.safe_load(args.data.read_text(encoding="utf-8"))
    split = "test" if data_cfg.get("test") else "val"
    out = args.out.resolve()

    model = YOLO(args.model)
    model.train(
        data=str(args.data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(out.parent),
        name=out.name,
        exist_ok=True,
        seed=args.seed,
    )
    best = out / "weights" / "best.pt"

    metrics = YOLO(str(best)).val(
        data=str(args.data), split=split, imgsz=args.imgsz, device=args.device, plots=False
    )
    names = metrics.names
    per_class = {
        names[int(c)]: round(float(ap), 4)
        for c, ap in zip(metrics.box.ap_class_index, metrics.box.ap50, strict=True)
    }
    result = {
        "date": datetime.date.today().isoformat(),
        "split": split,
        "data": str(args.data),
        "weights": str(best),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "seed": args.seed,
        "map50": round(float(metrics.box.map50), 4),
        "map50_95": round(float(metrics.box.map), 4),
        "precision": round(float(metrics.box.mp), 4),
        "recall": round(float(metrics.box.mr), 4),
        "ap50_per_class": per_class,
        "versions": {"ultralytics": ultralytics.__version__, "torch": torch.__version__},
    }
    (out / "metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"OK: {best}\nOK: {out / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
