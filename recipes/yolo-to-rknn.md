# Recipe: YOLOv8n → RKNN (INT8) 변환과 보드 추론

> ⚠️ **검증 전 초안.** BOARD-04, VIS-07을 진행하면서 실제 명령으로 교체한다. 기준 예제는 airockchip/rknn_model_zoo의 YOLOv8 예제다.

## 개념 3줄

- **ONNX**: 프레임워크 공용 모델 파일. PyTorch(.pt) → ONNX → RKNN 순서로 바꾼다.
- **INT8 양자화**: 32비트 소수 → 8비트 정수. 빠르고 작아지지만 정확도가 떨어질 수 있다.
- **캘리브레이션 데이터**: 양자화 범위를 정하는 샘플 이미지. **실제 주방 사진**이어야 정확도 손실이 작다.

## 1. 학습 (Colab)

```python
from ultralytics import YOLO
model = YOLO("yolov8n.pt")
model.train(data="kitchen.yaml", imgsz=640, epochs=100)   # 하이퍼파라미터는 실험 spec에 기록
```

## 2. ONNX export

RKNN용 export는 일반 export와 다르다. 후처리(DFL·NMS)를 그래프 밖으로 빼는 방식이 필요하다.
- 방법 A: rknn_model_zoo YOLOv8 예제 문서가 안내하는 export 절차 (확인 필요)
- 방법 B: Ultralytics의 RKNN export 기능 (지원 버전·실행 환경 확인 필요)

어느 쪽을 쓸지 결정하면 이 절과 [versions](../docs/conventions/versions.md)를 갱신한다.

## 3. RKNN 변환 (x86 Linux — Colab 또는 보드)

```python
from rknn.api import RKNN

rknn = RKNN()
rknn.config(mean_values=[[0, 0, 0]], std_values=[[255, 255, 255]], target_platform="rk3588")
rknn.load_onnx(model="best.onnx")
rknn.build(do_quantization=True, dataset="calib.txt")   # calib.txt: 캘리브레이션 이미지 경로 목록 (Train에서만)
rknn.export_rknn("best_int8.rknn")
rknn.release()
```

(파라미터는 model_zoo 예제 기준으로 확인 필요)

## 4. 보드 추론

```python
from rknnlite.api import RKNNLite

rknn = RKNNLite()
rknn.load_rknn("best_int8.rknn")
rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_0)       # YOLO는 core0 (architecture 문서)
outputs = rknn.inference(inputs=[img])                   # 전처리·후처리는 model_zoo 예제 코드 참고
```

## 5. 측정 (experiment-workflow)

- mAP50: fp32(.pt) / ONNX / INT8(.rknn, 보드) 3단계, 같은 Test Set
- 지연: 전처리 / NPU / 후처리 ms를 **따로** — 후처리(CPU)가 병목인 경우가 많다
- 결과는 [METRICS](../docs/METRICS.md)에 기록
