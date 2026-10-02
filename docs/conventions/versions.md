# Version Pinning

변환 툴과 보드 런타임은 **같은 릴리스**로 맞춘다. 버전 불일치는 "이유 없이 안 되는" 문제의 가장 흔한 원인이다.
이 표에 고정된 버전만 쓴다. 바꿀 때는 이슈 → PR로 바꾸고, 변경 이유를 PR에 적는다.

`고정 버전`은 실제로 설치해서 동작을 확인한 뒤 채운다 (BOARD-03, BOARD-06). `최신 릴리스`는 2026-10-02 공식 저장소에서 확인한 값으로, 설치 후보일 뿐 고정값이 아니다.

| 항목 | 고정 버전 | 최신 릴리스 (2026-10-02) | 제약 | 확인일 |
|---|---|---|---|---|
| 보드 OS 이미지 | | 학교 배포 이미지 (Ubuntu 22.04, Orange Pi 5 Plus) | 학교 특강2 p.8 | |
| 커널 / NPU 드라이버 | | RKNPU v0.9.8 (배포 이미지에 사전 설치) | RKLLM은 v0.9.8 이상 필요 | |
| RKNN-Toolkit2 (변환) | **2.3.2** + onnx 1.16.1 ([constraints](../../training/convert/rknn-constraints.txt)) | 2.3.2 | Linux x86_64 / aarch64, Python 3.6~3.12. aarch64는 onnxoptimizer 소스 빌드 필요 | 2026-10-02 (Docker linux/amd64, Python 3.11에서 YOLOv8n INT8 변환 성공, #13) |
| rknn-toolkit-lite2 / librknnrt (보드) | | 2.3.2 | aarch64, Python 3.7~3.12. 변환 툴과 같은 버전 | |
| rkllm-toolkit (변환) | **1.3.0 (학교 제공 도커)** | 1.3.1 (GitHub 최신) | Linux x86_64 전용, Python 3.10~3.12. 보드 런타임과 맞추기 위해 학교 도커 버전을 따른다 | 2026-10-02 (학교 특강2 p.4, 27) |
| librkllmrt (보드) | **1.3.0** | 1.3.1 | `run.sh build-demo` 산출물의 `lib/librkllmrt.so`를 쓴다 | 2026-10-02 (학교 특강2 p.27) |
| sherpa-onnx | **1.13.8** ([requirements](../../requirements.txt)) | 1.13.8 | NPU 실행은 별도 RKNN 빌드. 보드 배포 이미지에 든 버전은 보드 수령 후 확인 (확인 필요) | 2026-10-02 (Mac, SenseVoice int8 받아쓰기, #33) |
| ultralytics (학습) | **8.4.171** | 8.4.171 | RKNN export는 x86 Linux 전용이라 쓰지 않음 (포크 사용) | 2026-10-02 (Mac에서 학습·평가 확인, #19) |
| airockchip/ultralytics_yolov8 (export) | **4674fe6** + torch 2.4.1 · numpy<2 · onnx 1.16.1 ([export-requirements](../../training/yolo/export-requirements.txt)) | (포크, 커밋으로 고정) | 학습 환경과 별도 가상환경 | 2026-10-02 (Mac에서 export 성공, 출력 9개, #19) |
| Python (보드 / Colab) | | — | 위 제약의 교집합: **3.10~3.12** | |
| ESP32 Arduino core / ESP-IDF | | — | HW-03에서 결정 | |

개발 도구(pre-commit · ruff · pytest)는 [`requirements-dev.txt`](../../requirements-dev.txt)가 source of truth다.

코드가 생기면 Python 의존성은 `requirements*.txt` 또는 `pyproject.toml`이 source of truth가 되고, 이 표는 보드·변환 툴처럼 파일로 고정할 수 없는 항목만 남긴다.
