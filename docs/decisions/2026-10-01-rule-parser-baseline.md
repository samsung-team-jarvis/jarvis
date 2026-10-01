# Decision: 규칙 기반 파서를 LLM 비교 기준선·대체 경로로 사용

## Status
- Accepted

## Date
- 2026-10-01

## Context
- Action이 10개로 제한되어 있어 "LLM이 꼭 필요한가?"라는 질문을 받을 수 있다.
- LLM 출력이 JSON 스키마 검증에 실패하는 경우의 동작이 필요하다.

## Options
- Option A: LLM만 사용, 실패 시 ASK_CLARIFY
- Option B: 규칙 파서를 같은 Test Set의 비교 기준선으로 두고, LLM 검증 실패 시 규칙 파서로 대체

## Decision
- 선택한 안: B
- 선택 이유: LLM 도입 효과를 수치로 증명할 수 있고, 안정성이 올라간다. Walking Skeleton 단계의 규칙 파서를 그대로 재사용한다.

## Consequences
- 장점: 비교 근거 확보, 장애 시 동작 보장
- 단점: 규칙 파서 유지 비용
- 영향: PLAN FUS-02·FUS-06·LLM-09

## Verification
- 규칙 파서 vs LLM Action Accuracy (같은 Test Set, [METRICS](../METRICS.md))

## Revisit
- LLM이 규칙 파서를 넘지 못하면, 그 결과 자체를 분석 결과로 발표하고 LLM 역할을 재검토
