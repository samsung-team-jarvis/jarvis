# Decision Logs

여러 작업에 반복적으로 영향을 주는 구조·정책·기술 선택을 기록한다. 회고나 작업 일지가 아니다.
나중에 같은 결정을 다시 검토할 수 있도록 당시 맥락, 선택지, 결정, 영향, 재검토 조건을 남긴다.

## When To Write

- 모델·런타임·툴 버전 선택 (예: STT 모델 결정, LLM 후보 확정)
- 프로세스 구조, 통신 방식, NPU 배치처럼 여러 서비스에 영향을 주는 결정
- 안전 정책, 데이터 분할 정책처럼 되돌리기 어렵거나 평가 결과에 영향을 주는 결정
- 협업 방식(브랜치·PR·리뷰), agent harness 변경
- 대안이 있었고 tradeoff를 설명해야 같은 논의를 반복하지 않는 결정

아래는 decision log가 아니라 이슈·PR·spec에 남긴다: 작은 구현 상세, 단기 TODO, 개인 작업 기록.

## Naming

```text
YYYY-MM-DD-short-decision-title.md
```

## Logs

- [결정 사항 (초기 결정 대기 질문 Q-01~09, 문서 불일치)](./open-questions.md)
- [2026-10-01 Walking Skeleton 우선](./2026-10-01-walking-skeleton-first.md)
- [2026-10-01 안전 3계층](./2026-10-01-safety-layers.md)
- [2026-10-01 규칙 파서를 LLM 비교 기준선으로](./2026-10-01-rule-parser-baseline.md)
- [2026-10-01 협업 흐름: 이슈 → 브랜치 → PR → 머지](./2026-10-01-issue-branch-pr-flow.md)
- [2026-10-02 작업물 4개 분할과 담당](./2026-10-02-deliverables-split.md)
- [2026-10-02 서비스 간 통신은 로컬 MQTT](./2026-10-02-message-bus-mqtt.md)
- [2026-10-02 Function Call 스키마 v0.1 (장치·세기·타이머·함수 토큰 문법)](./2026-10-02-function-call-schema.md)
- [2026-10-02 LLM은 말 그대로 해석, 위험 판단은 Safety Guard](./2026-10-02-llm-literal-guard-decides.md)
- [2026-10-04 작업 재분배 (② → ①·③·④ 7건)](./2026-10-04-task-rebalance.md)
- [2026-10-05 시연 환경은 가상 주방(메타버스), 장치 8종](./2026-10-05-virtual-kitchen-demo.md)
- [2026-10-05 가상 주방 플랫폼은 Unity](./2026-10-05-unity-virtual-kitchen.md)

## Template

```markdown
# Decision: {title}

## Status
- Proposed / Accepted / Deprecated / Superseded (by: 링크)

## Date
- YYYY-MM-DD

## Context
- 어떤 문제를 해결하려는가? 근거 이슈·측정·문서는?
- 현재 제약은?

## Options
- Option A:
- Option B:

## Decision
- 선택한 안:
- 선택 이유:

## Consequences
- 장점 / 단점
- 영향을 받는 파일·문서·작업(PLAN ID):

## Verification
- 어떤 측정·실험으로 유효함을 확인했는가? (docs/METRICS.md 링크)
- 검증하지 못한 부분은?

## Revisit
- 어떤 조건이 바뀌면 다시 볼 것인가?
```

## Rules

- 결정은 현재 확인한 근거만 사용한다. 측정이 근거면 METRICS 항목을 링크한다.
- 관련 GitHub 이슈·PR을 링크한다.
- 결정이 바뀌면 기존 파일을 덮어쓰지 말고 `Status`를 `Superseded`로 바꾸고 새 파일을 링크한다.
