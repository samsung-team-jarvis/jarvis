# Decision: 안전 3계층

## Status
- Accepted

## Date
- 2026-10-01

## Context
- 소형·양자화 LLM은 정의되지 않은 Action이나 위험한 명령("과열 중인데 불 더 세게")을 낼 수 있다 (5주차 발표 p.15).
- Orange Pi 프로세스가 멈추면 장비가 켜진 채로 남을 수 있다.

## Options
- Option A: LLM 출력을 검증 후 바로 실행
- Option B: L0 ESP32 자체 안전장치 / L1 결정론적 Safety Guard / L2 LLM은 제안만

## Decision
- 선택한 안: B
- 세부:
  - L0 (ESP32 펌웨어): 온도 하드 리밋, Pi 하트비트 타임아웃 → 모든 출력 OFF. Pi와 무관하게 동작.
  - L1 (`safety_guard`): Action 화이트리스트, 파라미터 범위, 현재 State 기준 위험 명령 REJECT, 과열·방치 자동 차단.
  - L2 (`llm_svc`): 자연어 → Function Call 제안만.
  - 위험 감지 경로는 LLM을 거치지 않는다. 긴급 키워드는 LLM 없이 EMERGENCY_STOP.

## Consequences
- 장점: LLM 환각·Pi 장애가 물리 제어로 이어지지 않음. "초저지연 위험 대응" 주장의 근거.
- 단점: 규칙 유지보수 비용, ESP32 펌웨어 복잡도 증가
- 영향: [Architecture](../architecture/overview.md), PLAN FUS-03·FUS-04·FUS-09·HW-06·HW-09

## Verification
- Unsafe Action Rate (Guard 전/후), 위험 감지→차단 지연, 하트비트 끊김 테스트 ([METRICS](../METRICS.md))

## Revisit
- 해당 없음 (안전 정책은 완화하지 않는다)
