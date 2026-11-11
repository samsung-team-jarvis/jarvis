#!/usr/bin/env bash
# YOLOv8n RKNN 변환 (VIS-11): Linux 컨테이너에서 rknn-toolkit2를 설치하고
# rknn_model_zoo의 YOLOv8n ONNX(공식 배포본 = vision_svc의 models/yolov8n_rknn_zoo.onnx)를
# RK3588용 INT8 .rknn으로 바꾼 뒤, 시뮬레이터로 ONNX와 같은 사람을 찾는지 비교한다.
#
# 캘리브레이션: model_zoo COCO 사진 20장 중 앞 15장. 비교: 나머지 5장 + bus.jpg (캘리브레이션에 안 씀).
# 비교(CHECK=1)는 진짜 x86 Linux(Colab 등)에서만 켠다 — M1 Mac의 amd64 에뮬레이션에서는 시뮬레이터가
# "Illegal instruction"으로 죽는다 (2026-11-11 확인, 변환·export는 그 전에 끝난다). Mac에서 만든 모델의
# 정확도는 보드에서 ONNX와 비교한다 (python -m bench.board_day vision --compare --images <사진 폴더>).
#
# 기본은 Colab과 같은 linux/amd64 컨테이너 (M1 Mac에서는 에뮬레이션으로 실행, 느림).
# linux/arm64는 의존성 onnxoptimizer 0.3.8의 aarch64 휠이 없어 소스 빌드가 필요하므로 기본값으로 쓰지 않는다.
# 사용: bash training/convert/docker_rknn_yolo.sh   (PLATFORM=linux/arm64 로 바꿀 수 있음)
# 결과: training/convert/out/yolov8n_coco_i8.rknn (+ CHECK=1이면 yolov8n_coco_i8_check.json, git 제외)
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
RKNN_VERSION="${RKNN_VERSION:-2.3.2}"
CHECK="${CHECK:-0}"
IMAGE="${IMAGE:-python:3.11-slim}"
PLATFORM="${PLATFORM:-linux/amd64}"

docker run --rm --platform "$PLATFORM" \
  -v "$REPO_ROOT":/work \
  -e RKNN_VERSION="$RKNN_VERSION" \
  -e CHECK="$CHECK" \
  -w /work \
  "$IMAGE" bash -euo pipefail -c '
    apt-get update -qq && apt-get install -y -qq git wget libgl1 libglib2.0-0 >/dev/null
    pip install -q --upgrade pip
    # 공식 저장소의 버전 고정 requirements → 휠 순서로 설치 (PyPI 최신 의존성은 휠이 없을 수 있음)
    BASE=https://raw.githubusercontent.com/airockchip/rknn-toolkit2/v${RKNN_VERSION}/rknn-toolkit2/packages
    PYTAG=cp$(python -c "import sys; print(f\"{sys.version_info[0]}{sys.version_info[1]}\")")
    case "$(uname -m)" in
      aarch64)
        REQ="$BASE/arm64/arm64_requirements_${PYTAG}.txt"
        WHL="$BASE/arm64/rknn_toolkit2-${RKNN_VERSION}-${PYTAG}-${PYTAG}-manylinux_2_17_aarch64.manylinux2014_aarch64.whl" ;;
      x86_64)
        REQ="$BASE/x86_64/requirements_${PYTAG}-${RKNN_VERSION}.txt"
        WHL="$BASE/x86_64/rknn_toolkit2-${RKNN_VERSION}-${PYTAG}-${PYTAG}-manylinux_2_17_x86_64.manylinux2014_x86_64.whl" ;;
    esac
    echo "arch=$(uname -m) python=${PYTAG}"
    pip install -q -r "$REQ" -c /work/training/convert/rknn-constraints.txt
    pip install -q "$WHL"
    python -c "import rknn.api; print(\"rknn-toolkit2 import OK\")"

    cd /tmp
    git clone -q --depth 1 https://github.com/airockchip/rknn_model_zoo.git
    cd rknn_model_zoo/examples/yolov8/model
    bash download_model.sh
    ls -lh *.onnx

    cd /tmp/rknn_model_zoo/datasets/COCO
    head -15 coco_subset_20.txt > /tmp/calib.txt
    sed -i "s#^\./##; s#^#$PWD/#" /tmp/calib.txt
    CHECK_ARGS=""
    if [ "$CHECK" = 1 ]; then
      IMAGES=$(tail -5 coco_subset_20.txt | sed "s#^\./##; s#^#$PWD/#" | tr "\n" " ")
      CHECK_ARGS="--check /tmp/rknn_model_zoo/examples/yolov8/model/bus.jpg $IMAGES --report /work/training/convert/out/yolov8n_coco_i8_check.json"
    fi
    head -3 /tmp/calib.txt
    sha256sum /tmp/rknn_model_zoo/examples/yolov8/model/yolov8n.onnx

    mkdir -p /work/training/convert/out
    python /work/training/convert/yolo_onnx_to_rknn.py \
      --onnx /tmp/rknn_model_zoo/examples/yolov8/model/yolov8n.onnx \
      --dataset /tmp/calib.txt \
      --out /work/training/convert/out/yolov8n_coco_i8.rknn \
      --dtype i8 $CHECK_ARGS
  '
