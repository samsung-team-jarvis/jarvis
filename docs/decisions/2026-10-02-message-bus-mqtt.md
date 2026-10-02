# Decision: 서비스 간 통신은 로컬 MQTT(mosquitto)

## Status
- Accepted

## Date
- 2026-10-02

## Context
- 서비스(audio·vision·llm·fusion·guard·ble·recorder)가 별도 프로세스로 메시지를 주고받아야 한다 ([architecture](../architecture/overview.md) §4).
- 4명이 병렬 개발하고, 녹화·재생 테스트와 대시보드가 모든 메시지를 볼 수 있어야 한다.
- 모두 보드에서 오프라인으로 동작해야 하며 비용이 없어야 한다.

## Options
- Option A: MQTT (mosquitto 브로커, paho-mqtt) — 브로커 1개 설치, 토픽 구독·와일드카드, `mosquitto_sub`로 디버깅
- Option B: ZeroMQ — 브로커 없음, 빠름. 토픽 발견·디버깅 도구를 직접 만들어야 함
- Option C: 단일 프로세스 + Python Queue — 설치 없음. 한 모듈 장애가 전체 장애, 팀원별 독립 실행·녹화 재생 어려움

세 가지 모두 무료·오픈소스이고 보드에서 로컬로 동작한다.

## Decision
- 선택한 안: A (Q-06 추천안, 이현종 결정)
- 선택 이유: 디버깅(`mosquitto_sub -t '#' -v`)과 녹화(recorder가 `#` 구독)가 쉽고, 서비스별 독립 실행·재시작이 된다. 대시보드(UI-01)도 같은 버스를 구독하면 된다.
- 통신 방식은 [`common/bus.py`](../../common/bus.py) 한 곳에만 둔다. 서비스는 `connect()` / `publish` / `subscribe`만 쓰므로, 방식을 바꿔도 서비스 코드는 바뀌지 않는다. 테스트·하드웨어 없는 개발용으로 같은 인터페이스의 `memory://` 버스를 둔다.

## Consequences
- 장점: 디버깅·녹화·대시보드 연결 용이, 프로세스 격리
- 단점: 보드에 mosquitto 설치·실행이 필요하다 (BOARD-07 런처에 포함). 브로커가 죽으면 모든 통신이 끊긴다 → 안전 계층 L0(ESP32 하트비트 타임아웃)이 이 경우에도 장비를 끈다.
- 영향: INFRA-03(`common/`), INFRA-05(recorder), BOARD-07(런처), UI-01

## Verification
- 2026-10-02 Mac + Docker mosquitto 2: memory·MQTT 단일 프로세스 selftest, 프로세스 간 pub/sub, pytest 통합 테스트 통과 (#20)
- 보드에서의 지연은 미측정 (INFRA-06에서 측정)

## Revisit
- 보드에서 측정한 버스 지연이 E2E 지연 예산을 크게 차지하면 ZeroMQ 등 재검토
