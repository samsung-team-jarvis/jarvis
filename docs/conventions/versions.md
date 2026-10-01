# Version Pinning

변환 툴과 보드 런타임은 **같은 릴리스**로 맞춘다. 버전 불일치는 "이유 없이 안 되는" 문제의 가장 흔한 원인이다.
이 표에 고정된 버전만 쓴다. 바꿀 때는 이슈 → PR로 바꾸고, 변경 이유를 PR에 적는다.

BOARD-03에서 채운다.

| 항목 | 버전 | 확인 방법 | 확인일 |
|---|---|---|---|
| 보드 OS 이미지 | | | |
| 커널 / NPU 드라이버 | | | |
| RKNN-Toolkit2 (변환) | | | |
| rknn-toolkit-lite2 / librknnrt (보드) | | | |
| rkllm-toolkit (변환) | | | |
| librkllmrt (보드) | | | |
| sherpa-onnx | | | |
| ultralytics | | | |
| Python (보드 / Colab) | | | |
| ESP32 Arduino core / ESP-IDF | | | |

코드가 생기면 Python 의존성은 `requirements*.txt` 또는 `pyproject.toml`이 source of truth가 되고, 이 표는 보드·변환 툴처럼 파일로 고정할 수 없는 항목만 남긴다.
