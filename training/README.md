# training

모델 학습·변환 코드. 가중치·데이터는 git에 넣지 않고 팀 Drive(`MyDrive/jarvis/models`)에 둔다.

| 경로 | 내용 | 실행 환경 |
|---|---|---|
| `colab/train_yolo.ipynb` | **YOLO 학습 → Test 평가 → RKNN용 ONNX → 캘리브레이션 목록** (설정 셀만 수정) | Colab (GPU) |
| `colab/convert_rknn.ipynb` | RKNN-Toolkit2 설치 + ONNX → `.rknn` 변환 | Colab (CPU) |
| `colab/convert_rkllm.ipynb` | rkllm-toolkit 설치 + 소형 LLM → `.rkllm` 샘플 변환 | Colab (GPU 권장) |
| `yolo/train_eval.py` | 학습 + Test 평가 → `metrics.json` | 어디서나 (GPU 권장) |
| `yolo/export_rknn_onnx.sh` | `.pt` → RKNN용 ONNX (airockchip 포크) | export 전용 환경 (`yolo/export-requirements.txt`) |
| `yolo/make_calib_list.py` | Train 이미지로 캘리브레이션 목록 (`--copy`로 이미지 동봉) | 어디서나 |
| `convert/yolo_onnx_to_rknn.py` | ONNX → RKNN 변환 스크립트 (목록의 상대 경로는 목록 파일 기준) | Linux x86_64 (또는 aarch64, 아래 주의) |
| `convert/hf_to_rkllm.py` | HF LLM → RKLLM 변환 스크립트 | Linux x86_64 · Python 3.10~3.12 |
| `convert/docker_rknn_smoke.sh` | Mac에서 Docker로 RKNN 변환 확인 | Docker (linux/amd64 에뮬레이션) |

## 주의

- **YOLO 학습과 RKNN용 export는 다른 환경**이다: 포크가 numpy<2와 옛 ONNX exporter(torch ≤ 2.8)를 요구해서, 노트북은 export용 가상환경(`uv`)을 따로 만든다.
- **변환 노트북 두 개는 각각 새 런타임에서** 실행한다. rkllm-toolkit(torch 2.6.0, protobuf ≥ 4.21)과 rknn-toolkit2(torch ≤ 2.2.0, protobuf 3.20.3)의 의존성이 충돌한다.
- Linux aarch64(보드 포함)에서 RKNN-Toolkit2 **전체**(변환용)를 설치하려면 의존성 `onnxoptimizer==0.3.8`을 소스 빌드해야 한다 (PyPI에 aarch64 휠 없음, 2026-10-02 확인). 변환은 Colab에서 하고, 보드에는 추론용 `rknn-toolkit-lite2`만 설치한다.
- 절차·근거: [yolo-to-rknn](../recipes/yolo-to-rknn.md), [llm-to-rkllm](../recipes/llm-to-rkllm.md)
