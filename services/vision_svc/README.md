# vision_svc — 화면 물체 인식 (사람 감지)

화면에서 물체를 찾아 `vision/objects`로 발행한다 ([interfaces](../../docs/architecture/interfaces.md) §2). 기본은 **COCO 사전학습 YOLOv8n으로 사람(`person`)만** 발행한다 — 방치 판단(가열 장치 켜짐 + 사람 없음)에 필요한 것은 "조리 구역에 사람이 있는가"이기 때문이다 ([decision](../../docs/decisions/2026-10-29-vision-pretrained-person.md)). PLAN VIS-08.

```text
kitchen/frame (가상 주방, JPEG) ─┐
노트북 카메라 · 이미지 폴더 ─────┴▶ 전처리(640×640, 비율 유지) ─▶ 추론 ─▶ 후처리(DFL·NMS) ─▶ vision/objects
                                                          .onnx: onnxruntime CPU (노트북)
                                                          .rknn: RKNN NPU core0 (보드)
```

## 모델 받기 (한 번만)

보드용 `.rknn`은 아래 ONNX를 INT8로 바꾼 것이다: Mac에서 `bash training/convert/docker_rknn_yolo.sh` → `training/convert/out/yolov8n_coco_i8.rknn`을 보드의 `models/`로 복사 ([yolo-to-rknn](../../recipes/yolo-to-rknn.md)).


`models/`는 git 제외. rknn_model_zoo의 YOLOv8n ONNX(12.7 MB, Ultralytics YOLOv8 · AGPL-3.0)를 받는다 — 보드 RKNN 변환([recipe](../../recipes/yolo-to-rknn.md))과 같은 출력 형식이라 후처리 코드 하나로 노트북·보드에서 쓴다.

```bash
mkdir -p models
curl -L -o models/yolov8n_rknn_zoo.onnx \
  https://ftrg.zbox.filez.com/v2/delivery/data/95f00b0fc900458ba134f8b180b3f7a1/examples/yolov8/yolov8n.onnx
```

## 실행

```bash
python -m services.vision_svc                          # 가상 주방 화면(kitchen/frame), 버스는 JARVIS_BUS
python -m services.vision_svc --input camera           # 노트북 카메라 (macOS는 터미널의 카메라 권한 필요)
python -m services.vision_svc --input data/frames/     # 이미지 폴더(또는 파일)를 한 번 흘림
python -m services.vision_svc detect photo.jpg         # 버스 없이 결과만 (모든 COCO 클래스)
python -m services.vision_svc --classes person,bowl,oven   # 발행할 클래스 바꾸기
python -m services.vision_svc --model models/yolov8n_coco_i8.rknn --input camera   # 보드 NPU
```

- 엔진은 모델 확장자로 고른다: `.onnx` → onnxruntime CPU, `.rknn` → NPU (rknn-toolkit-lite2, 보드에만 있음 — [board-setup](../../recipes/board-setup.md) §4). NPU 코어는 `--npu-core` (기본 `0`, `1`·`2`·`all`·`auto`).

- 1초에 4장(`--fps`), 추론 CPU 2스레드(`--threads`, 노트북에서 STT·LLM과 나눠 쓴다).
- 가상 주방 화면은 가장 최근 것만 인식한다 (밀리면 건너뛴다).
- **화면이 끊기면** (VIS-12): 1초 넘게 화면이 없으면 경고를 한 번 남기고(`… 1.2초째 없음 — 상황 인식은 사람이 없는 것으로 본다`), 다시 들어오면 몇 초 끊겼는지 남긴다. 카메라는 2초마다 다시 연다 (USB 웹캠이 빠졌다 꽂힘). 화면이 끊긴 동안 `fusion_svc`는 사람이 없는 것으로 보므로 60초 뒤 자동 차단된다 — 불이 꺼진 이유를 이 로그로 확인한다.
- 노트북 시연 설정([`launch_demo.yaml`](../../scripts/launch_demo.yaml))은 카메라 입력으로 띄운다.

## 발행 내용

| 필드 | 뜻 |
|---|---|
| `objects` | `[{cls, conf, bbox: [x1, y1, x2, y2]}]` — `cls`는 COCO 이름(기본 `person`만), `bbox`는 원본 화면 픽셀 |
| `frame_id` | 이 서비스가 처리한 순번 (0부터) |
| `pre_ms` · `npu_ms` · `post_ms` | 전처리 · 추론 · 후처리 시간. 노트북에서는 `npu_ms`가 CPU 추론 시간이다 (필드 이름은 규격 그대로) |

`session_id`는 이 서비스의 것이다 (화면은 발화에서 온 메시지가 아니다). `system/heartbeat`는 1초마다.

## 코드

| 파일 | 하는 일 |
|---|---|
| `detect.py` | 전처리(`letterbox` → RGB 640×640 uint8, `to_tensor`)·후처리(DFL·클래스별 NMS) — numpy만, rknn_model_zoo `yolov8.py`와 같은 계산 |
| `engine.py` | `OnnxEngine`(CPU)·`RknnEngine`(NPU), 확장자로 고르는 `load()`. 엔진마다 입력 형식이 달라 `prepare()`로 맞춘다 (ONNX: 1×3×640×640 float 0~1, RKNN: 1×640×640×3 uint8) |
| `service.py` | `VisionService` — 클래스 걸러 발행 |
| `camera.py` | `Camera`(읽기 실패 시 다시 열기)·`GapWatch`(화면 끊김 경고) |

## 확인 기록 (Mac, 2026-10-29, #122)

- rknn_model_zoo 예제 사진(bus.jpg): person 0.88 · 0.88 · 0.87 · 0.33, bus 0.85 — 예제 문서의 결과와 같은 물체·위치
- MQTT(mosquitto 2) 위 `kitchen/frame` 입력: 사람 사진 8장 → 빈 화면 8장을 1초에 4장 보냄 → 16건 모두 발행, 앞 8건 person 4명 · 뒤 8건 없음
- 시간 (M1 Pro, onnxruntime 1.31.1 CPU 2스레드, 640×640 입력): 전처리 2~4 · 추론 75~91 · 후처리 3~5 ms
- **확인 안 한 것**: 노트북 카메라 입력 (이 실행 환경에 카메라 권한이 없었다), 가상 주방(Unity) 화면 속 사람 인식률, 보드 RKNN
