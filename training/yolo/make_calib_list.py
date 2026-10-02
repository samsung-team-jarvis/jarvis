"""RKNN INT8 양자화용 캘리브레이션 이미지 목록(dataset.txt) 생성.

Train 세트 이미지에서만 무작위로 뽑는다 (Test 이미지를 쓰면 평가가 오염된다).

사용:
    python training/yolo/make_calib_list.py --images data/train/images --n 200 --out out/dataset.txt
    # 다른 런타임으로 옮길 때: 이미지를 out 옆 calib/에 복사하고 상대 경로로 기록
    python training/yolo/make_calib_list.py --images data/train/images --out out/dataset.txt --copy
"""

import argparse
import pathlib
import random
import shutil
import sys

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--images", required=True, type=pathlib.Path, help="Train 이미지 폴더")
    parser.add_argument("--n", type=int, default=200)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--copy", action="store_true", help="out 옆 calib/에 복사, 상대 경로 기록")
    args = parser.parse_args()

    images = sorted(p.resolve() for p in args.images.rglob("*") if p.suffix.lower() in IMAGE_EXTS)
    if not images:
        print(f"이미지가 없습니다: {args.images}")
        return 1
    picked = random.Random(args.seed).sample(images, min(args.n, len(images)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.copy:
        calib_dir = args.out.parent / "calib"
        calib_dir.mkdir(exist_ok=True)
        lines = []
        for i, src in enumerate(picked):
            dst = calib_dir / f"{i:04d}{src.suffix.lower()}"
            shutil.copy2(src, dst)
            lines.append(f"calib/{dst.name}")
    else:
        lines = [str(p) for p in picked]
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"OK: {args.out} ({len(picked)}장 / Train {len(images)}장)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
