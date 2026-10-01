# Decision: 모든 작업은 이슈 → 브랜치 → PR → 머지

## Status
- Accepted

## Date
- 2026-10-01

## Context
- 4명이 병렬로 작업하고, 작업 근거(무엇을 왜 했는지, 무엇을 측정했는지)를 학기 말 보고서와 발표에 써야 한다.
- `main`은 브랜치 보호(직접 push 금지, PR 승인 1명)가 걸려 있다.

## Options
- Option A: 브랜치·PR만 사용, 이슈는 선택
- Option B: 모든 작업은 GitHub 이슈부터 만들고, 이슈 번호로 브랜치·커밋·PR을 연결

## Decision
- 선택한 안: B
- 선택 이유: 이슈가 작업 단위·완료 기준·논의 기록의 단일 위치가 된다. PR의 `Closes #N`으로 완료가 자동 기록된다.
- PLAN 작업 ID(예: `STT-01`)는 이슈 제목에 넣고, 이슈 번호가 브랜치·커밋·PR의 키가 된다. 형식은 [Git Convention](../conventions/git.md).

## Consequences
- 장점: 추적 가능성, 보고서 근거 확보
- 단점: 작은 작업에도 이슈 생성 비용
- 영향: [Git Convention](../conventions/git.md), `.github/ISSUE_TEMPLATE`, `.github/pull_request_template.md`

## Verification
- 첫 적용: 이슈 #1 (harness 세팅)

## Revisit
- 오탈자 수정 같은 초소형 변경까지 이슈를 만드는 게 부담되면 예외 규칙 검토
