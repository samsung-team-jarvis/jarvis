# Coding Convention

코드가 생기기 전 초안이다. 첫 서비스 코드(INFRA-03)를 작성하면서 실제 설정 파일(`pyproject.toml` 등)을 source of truth로 옮긴다.

## Python (서비스·학습·측정 스크립트)

- Python 3.10~3.12 (rkllm-toolkit·rknn-toolkit-lite2 지원 범위의 교집합. [versions](./versions.md)에서 확정)
- 포맷·린트: `ruff format`, `ruff check` (pre-commit과 CI에서 실행)
- 네이밍: 모듈·함수·변수 `snake_case`, 클래스 `PascalCase`, 상수 `BIG_SNAKE_CASE`
- 타입 힌트를 공개 함수 시그니처에 붙인다.
- 서비스 간 메시지는 `common`의 `Envelope.new()`로 만들고 `connect()`로 얻은 버스로만 주고받는다. dict를 직접 조립하거나 MQTT를 직접 쓰지 않는다 ([interfaces](../architecture/interfaces.md)).
- 로그는 `print` 대신 `common`의 로거를 쓴다. 측정에 쓰는 시각은 `time.monotonic()`.
- 설정값(장치 경로, 임계값, 모델 경로)은 코드에 하드코딩하지 않고 설정 파일·환경변수로 뺀다.
- 하드웨어가 없어도 실행되도록 입력 소스는 교체 가능하게 만든다 (실제 마이크 / wav 파일 / 가짜 메시지).

## 안전 관련 코드

- `safety_guard`와 가상 주방 쪽 안전장치는 결정론적 규칙만 쓴다. 학습 모델·랜덤 요소 금지.
- 안전 규칙을 바꾸는 PR은 PR Point에 명시하고, 관련 테스트를 함께 추가한다.

## C/C++ (필요 시 성능 경로)

- Rockchip 예제 코드 구조를 따르고, 예제에서 가져온 코드는 출처 주석을 남긴다.

## 가상 주방 스크립트

- 언어·도구는 플랫폼을 정한 뒤 확정한다 (HW-13).
- 임계값(온도 상한, 생존 신호 타임아웃)은 상단 상수로 모은다.
- 안전 상태(가열 장치 OFF)가 기본값이다. 시작 직후·연결 끊김·오류 시 항상 안전 상태로 간다.

## 노트북 (Colab)

- `training/` 아래 두고, 첫 셀에 사용한 툴 버전과 실행 환경을 출력한다.
- 출력이 큰 셀은 커밋 전에 결과를 지운다.
