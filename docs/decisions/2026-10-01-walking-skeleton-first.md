# Decision: Walking Skeleton 우선 개발

## Status
- Accepted

## Date
- 2026-10-01

## Context
- 4명이 STT·비전·LLM·센서·BLE·하드웨어를 병렬 개발한다. 모듈별 완성도는 높은데 한 번도 연결되지 않은 상태로 막판에 통합하다 실패하는 것이 가장 큰 리스크다.

## Options
- Option A: 모듈별로 완성한 뒤 마지막에 통합
- Option B: 가장 단순한 구현(규칙 파서, 기본 모델, 가짜 센서)으로 끝까지 먼저 연결한 뒤 부품을 하나씩 교체

## Decision
- 선택한 안: B
- 선택 이유: 통합 리스크를 초반에 드러내고, 매 단계 시연 가능한 결과물이 생긴다. E2E 지연 측정도 초반부터 가능하다.

## Consequences
- 장점: 막판 통합 실패 방지, 인터페이스 문제 조기 발견
- 단점: 초반에 "버릴" 단순 구현(규칙 파서 등)에 시간이 든다. 규칙 파서는 LLM 비교 기준선으로 재사용한다.
- 영향: [PLAN](../PLAN.md) Phase 2 (Gate 2)

## Verification
- Gate 2 시연(말 → LED)과 E2E 지연 로그

## Revisit
- 일정상 Phase 2 진입이 크게 늦어지면 범위 축소 재검토
