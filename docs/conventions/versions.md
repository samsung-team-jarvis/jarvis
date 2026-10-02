# Version Pinning

변환 툴과 보드 런타임은 **같은 릴리스**로 맞춘다. 버전 불일치는 "이유 없이 안 되는" 문제의 가장 흔한 원인이다.
이 표에 고정된 버전만 쓴다. 바꿀 때는 이슈 → PR로 바꾸고, 변경 이유를 PR에 적는다.

`고정 버전`은 실제로 설치해서 동작을 확인한 뒤 채운다 (BOARD-03, BOARD-06). `최신 릴리스`는 2026-10-02 공식 저장소에서 확인한 값으로, 설치 후보일 뿐 고정값이 아니다.

| 항목 | 고정 버전 | 최신 릴리스 (2026-10-02) | 제약 | 확인일 |
|---|---|---|---|---|
| 보드 OS 이미지 | | — | 보드 모델(5 / 5 Plus)에 맞는 이미지 | |
| 커널 / NPU 드라이버 | | — | RKLLM 1.3.1은 NPU 드라이버 **v0.9.8 이상** | |
| RKNN-Toolkit2 (변환) | | 2.3.2 | Linux x86_64 / aarch64, Python 3.6~3.12 | |
| rknn-toolkit-lite2 / librknnrt (보드) | | 2.3.2 | aarch64, Python 3.7~3.12. 변환 툴과 같은 버전 | |
| rkllm-toolkit (변환) | | 1.3.1 | Linux x86_64 전용, Python 3.10~3.12 | |
| librkllmrt (보드) | | 1.3.1 | 변환 툴과 같은 버전 | |
| sherpa-onnx | | 1.13.8 | NPU 실행은 별도 RKNN 빌드 | |
| ultralytics | | 8.4.171 | RKNN export는 x86 Linux 전용 | |
| airockchip/ultralytics_yolov8 | | (포크, 커밋으로 고정) | YOLOv8 RKNN용 ONNX export | |
| Python (보드 / Colab) | | — | 위 제약의 교집합: **3.10~3.12** | |
| ESP32 Arduino core / ESP-IDF | | — | HW-03에서 결정 | |

개발 도구(pre-commit · ruff · pytest)는 [`requirements-dev.txt`](../../requirements-dev.txt)가 source of truth다.

코드가 생기면 Python 의존성은 `requirements*.txt` 또는 `pyproject.toml`이 source of truth가 되고, 이 표는 보드·변환 툴처럼 파일로 고정할 수 없는 항목만 남긴다.
