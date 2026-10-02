#!/usr/bin/env bash
# 학습한 YOLOv8 .pt → RKNN용 ONNX (airockchip/ultralytics_yolov8 포크, recipes/yolo-to-rknn.md 방법 A).
# 포크는 후처리·DFL을 그래프 밖으로 빼서 NPU에 맞춘 ONNX(출력 9개)를 만든다.
#
# 준비: export 전용 가상환경에 training/yolo/export-requirements.txt 설치 (학습 환경과 분리)
# 사용: PYTHON=<export 환경의 python> bash training/yolo/export_rknn_onnx.sh <best.pt> <out.onnx>
set -euo pipefail

PT="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUT="$2"
PYTHON="${PYTHON:-python}"
FORK_SHA="${FORK_SHA:-4674fe6e003dfbc5f2250d3b39dd31faaf7a9877}"  # 2024-09 main (docs/conventions/versions.md)
WORK="${WORK:-${TMPDIR:-/tmp}/ultralytics_yolov8}"

# 환경 확인: 학습 환경에서 잘못 실행하는 경우를 막는다
"$PYTHON" - <<'PY'
import sys
import numpy, torch
bad = []
if int(numpy.__version__.split(".")[0]) >= 2:
    bad.append(f"numpy {numpy.__version__} (포크는 numpy<2 필요)")
if tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2]) >= (2, 9):
    bad.append(f"torch {torch.__version__} (2.9 이상은 ONNX exporter가 달라짐)")
if bad:
    print("export 환경이 아닙니다: " + ", ".join(bad))
    print("training/yolo/export-requirements.txt로 만든 별도 가상환경의 python을 PYTHON에 지정하세요.")
    sys.exit(1)
PY

if [ ! -d "$WORK/.git" ]; then
  git clone -q https://github.com/airockchip/ultralytics_yolov8.git "$WORK"
fi
CFG=ultralytics/cfg/default.yaml
git -C "$WORK" checkout -q -- "$CFG"  # 이전 실행이 중간에 실패해 남은 수정을 되돌린다
git -C "$WORK" fetch -q origin "$FORK_SHA"
git -C "$WORK" checkout -q "$FORK_SHA"

# 포크 설정 파일의 model 경로를 학습 결과로 바꾼다 (format: rknn, imgsz: 640 이 기본).
# 끝나면(실패해도) git으로 원본으로 되돌린다.
trap 'git -C "$WORK" checkout -q -- "$CFG"' EXIT
sed -i.bak "s|^model: .*|model: ${PT} # set by export_rknn_onnx.sh|" "$WORK/$CFG" && rm -f "$WORK/$CFG.bak"

(cd "$WORK" && PYTHONPATH=./ "$PYTHON" ./ultralytics/engine/exporter.py)

mkdir -p "$(dirname "$OUT")"
mv "${PT%.pt}.onnx" "$OUT"
echo "OK: $OUT"
