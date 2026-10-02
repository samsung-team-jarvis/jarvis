# Recipe: YOLOv8n → RKNN (INT8) 변환과 보드 추론

> 2026-10-02 공식 저장소·문서로 절차를 확인했다 (아래 출처). 실제 실행 결과(BOARD-04, VIS-07)는 아직 없다 — 실행하면서 막힌 곳을 이 문서에 추가한다.

## 개념 3줄

- **ONNX**: 프레임워크 공용 모델 파일. PyTorch(.pt) → ONNX → RKNN 순서로 바꾼다.
- **INT8 양자화**: 32비트 소수 → 8비트 정수. 빠르고 작아지지만 정확도가 떨어질 수 있다.
- **캘리브레이션 데이터**: 양자화 범위를 정하는 샘플 이미지. **실제 주방 사진**이어야 정확도 손실이 작다.

## 어디서 실행하나

| 단계 | 실행 환경 | 근거 |
|---|---|---|
| 학습 | Colab (GPU) | |
| ONNX export (방법 A) | 어디서나 (Python) | airockchip/ultralytics_yolov8 |
| ONNX → RKNN 변환 | **Linux x86_64 또는 Linux aarch64(보드)**. macOS 휠 없음 → Mac에서는 불가 | rknn-toolkit2 `packages/` (v2.3.2, Python 3.6~3.12) |
| 보드 추론 | 보드 (`rknn-toolkit-lite2`, aarch64 · Python 3.7~3.12) | rknn-toolkit-lite2 `packages/` |

## 1. 학습 (Colab)

```python
from ultralytics import YOLO

model = YOLO("yolov8n.pt")
model.train(data="kitchen.yaml", imgsz=640, epochs=100)  # 하이퍼파라미터는 실험 spec에 기록
```

## 2. ONNX export — 방법 A (기본으로 사용)

rknn_model_zoo YOLOv8 예제는 **airockchip/ultralytics_yolov8 포크**로 export한다. 이 포크는 후처리를 그래프 밖으로 빼고 DFL을 제거하고 score-sum 분기를 추가한다 (NPU에서 빠르게 돌리기 위한 구조). 기본 입력 크기는 640×640.

```bash
git clone https://github.com/airockchip/ultralytics_yolov8.git
cd ultralytics_yolov8
# ultralytics/cfg/default.yaml 의 model 항목을 학습한 best.pt 경로로 수정
export PYTHONPATH=./
python ./ultralytics/engine/exporter.py
```

### 방법 B — Ultralytics 공식 RKNN export (참고)

`model.export(format="rknn", name="rk3588")`가 있지만 **x86 Linux에서만** 된다(ARM64·보드에서 export 불가). 기본은 FP16이고 INT8은 검출(detect) 모델만 지원한다. rknn-toolkit2 ≥ 2.3.2 필요. 후처리 코드가 model_zoo 예제와 다를 수 있어서, 이 프로젝트는 방법 A를 기본으로 한다.

## 3. RKNN 변환

model_zoo 예제 스크립트를 그대로 쓰는 것이 가장 안전하다.

```bash
# rknn_model_zoo/examples/yolov8/python
python convert.py best.onnx rk3588 i8 best_int8.rknn     # i8(기본) | u8 | fp
```

직접 쓸 때의 API (rknn-toolkit2 예제 기준):

```python
from rknn.api import RKNN

rknn = RKNN(verbose=True)
rknn.config(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]], target_platform="rk3588")
rknn.load_onnx(model="best.onnx")
rknn.build(do_quantization=True, dataset="./dataset.txt")
rknn.export_rknn("best_int8.rknn")
rknn.release()
```

`dataset.txt`: 캘리브레이션 이미지 경로를 **한 줄에 하나씩** 적은 텍스트 파일. Train 세트에서만 뽑는다.

## 4. 보드 추론

```python
from rknnlite.api import RKNNLite

rknn = RKNNLite()
rknn.load_rknn("best_int8.rknn")
rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0)  # YOLO는 core0 (architecture 문서)
outputs = rknn.inference(inputs=[img])  # 전처리·후처리는 model_zoo yolov8 예제 코드 사용
```

## 5. 측정 (experiment-workflow)

- mAP50: fp32(.pt) / ONNX / INT8(.rknn, 보드) 3단계, 같은 Test Set
- 지연: 전처리 / NPU / 후처리 ms를 **따로** — 후처리(CPU)가 병목인 경우가 많다
- 결과는 [METRICS](../docs/METRICS.md)에 기록

## 출처 (2026-10-02 확인)

- https://github.com/airockchip/rknn_model_zoo/tree/main/examples/yolov8
- https://github.com/airockchip/ultralytics_yolov8 (RKOPT_README.md)
- https://github.com/airockchip/rknn-toolkit2 (README, `rknn-toolkit2/packages`, `rknn-toolkit-lite2/examples/resnet18/test.py`, `examples/onnx/yolov5`)
- https://docs.ultralytics.com/integrations/rockchip-rknn/
