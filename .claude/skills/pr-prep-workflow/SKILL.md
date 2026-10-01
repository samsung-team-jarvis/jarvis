---
name: pr-prep-workflow
description: 브랜치 작업을 마치고 push와 PR을 만들 때 사용합니다. PR 제목·본문을 템플릿 기준으로 작성하고 머지 전 체크리스트를 점검합니다.
---

# PR 준비 워크플로

## 읽기 전략

- `docs/workflows/pull-request-writing.md`
- `.github/pull_request_template.md`
- `docs/conventions/git.md` (PR 제목 형식)

## 절차

1. 커밋이 정리됐는지 확인한다: `git log --oneline main..HEAD`
2. 머지 전 체크리스트(`pull-request-writing.md`)를 하나씩 확인한다. 안 된 항목은 PR 본문 Risk / Follow-up에 적는다.
3. push: `git push -u origin <branch>`
4. 제목: `[PREFIX](scope): #N work summary`
5. 본문: 템플릿 섹션 구조를 유지하고 문단형으로 쓴다.
   - `Related Issues`에 `Closes #N`
   - `Verification`에는 실제 실행한 것만, 실행 장소와 함께
   - `Measurement`에는 실측값과 측정 조건만. 측정이 없으면 "없음"
6. 생성: `gh pr create --title "..." --body-file <file>`
7. 생성 후 확인: 라벨 자동 부착, assignee, CI 결과 (`gh pr checks`)

## 하지 말 것

- 실행하지 않은 검증을 성공처럼 쓰기
- 리뷰 승인 없이 머지 (사용자가 명시적으로 지시한 경우만 관리자 머지)
- squash 머지 (나눠 둔 커밋 보존을 위해 merge commit 사용)
