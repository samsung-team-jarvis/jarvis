---
name: task-workflow
description: PLAN 작업 ID(예: STT-01) 또는 새 작업을 시작할 때 사용합니다. 이슈 생성 → 브랜치 → 구현 → 검증 → PLAN 갱신 → 커밋 → PR → 머지까지의 순서를 안내합니다.
---

# 작업 워크플로

## 목적

모든 작업을 같은 흐름(이슈 → 브랜치 → PR → 머지)으로 진행하고, 완료 근거를 남긴다.

## 읽기 전략

항상 확인한다.

- `docs/PLAN.md` — 해당 작업 ID의 완료 기준·선행 작업
- `docs/conventions/git.md` — 브랜치·커밋·PR 형식

작업 종류에 따라 추가로 확인한다.

- 서비스 코드: `docs/architecture/interfaces.md`, `docs/conventions/coding.md`, `recipes/add-service.md`
- 측정·학습·변환: `docs/workflows/experiment.md`, 관련 `recipes/*`
- 구조·정책 변경: `docs/decisions/index.md`

## 절차

1. **작업 확인**: PLAN에서 ID를 찾아 완료 기준·선행 작업·**담당**을 읽는다. 담당이 현재 사용자(`git config user.name`, GitHub 아이디는 `docs/onboarding.md` 표)와 다르면 진행 전에 확인한다. 선행이 미완료면 사용자에게 알린다. PLAN에 없는 작업이면 PLAN에 추가할지 먼저 묻는다.
2. **이슈 생성**: 제목 `[ID] 작업 요약`, 본문에 목적·작업 체크리스트·완료 기준. `.github/ISSUE_TEMPLATE`의 형식을 따른다.
3. **브랜치 생성**: `main` 최신화 후 `prefix/{scope}/{이슈번호}-work-summary`.
4. **스펙 판단**: 새 서비스는 `templates/service.spec.md`, 측정·학습은 `templates/experiment.spec.md`를 먼저 채운다. 단순 수정은 생략한다.
5. **구현**: 요청 범위 밖 기능·추상화를 추가하지 않는다. 하드웨어 없이도 돌 수 있게 입력을 교체 가능하게 만든다.
6. **검증**: 실제로 실행한 검증만 기록한다. 실행 장소(Mac / Colab / 보드 / 가상 주방)를 함께 적는다. 보드가 필요한데 접근할 수 없으면 "보드 미검증"으로 남긴다.
7. **문서 갱신**: PLAN 체크(완료 시), METRICS(측정 시), interfaces 변경 이력(규격 변경 시), decision log(결정 시).
8. **커밋**: `commit-planning-workflow`로 단위를 나눠 커밋한다.
9. **PR**: `pr-prep-workflow`로 본문 작성, `Closes #N` 포함.
10. **머지**: 리뷰 승인 1명 후 merge commit으로 머지. 머지는 사용자가 지시했을 때만 한다.

## 하지 말 것

- `main`에 직접 커밋·push
- 측정하지 않은 수치를 문서·PR에 기록
- LLM 출력이 Safety Guard를 우회하는 경로 추가
- 모델 가중치·원본 데이터 커밋

## 사용자에게

사용자는 온디바이스 분야가 처음이다. 새 개념이 나오면 한두 줄로 설명하고 진행한다.
