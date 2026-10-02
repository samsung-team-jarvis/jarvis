# JARVIS Docs

구조, 컨벤션, 작업 절차, agent harness를 분리해서 관리한다.
`README.md`는 빠른 진입점으로 유지하고, 세부 규칙은 이 문서들을 기준으로 갱신한다.

## Start Here

- [팀원 온보딩 체크리스트](./onboarding.md)
- [비용 목록 (구매 필요 · 무료 · 유료 주의)](./budget.md)
- [산출물 규칙·등록부 (데이터·모델 파일 전달)](./artifacts.md)
- [학교 제공 자료 (마음AI 특강·SUDA 데이터) 요약](./school-materials.md)

## Plan & Metrics

- [Plan (작업 백로그)](./PLAN.md)
- [Metrics (지표·측정 결과)](./METRICS.md)

## Architecture

- [Overview (전체 구조·안전 계층·자원 배치)](./architecture/overview.md)
- [Interfaces (메시지·Function Call·BLE 규격)](./architecture/interfaces.md)
- [Hardware (보드 비교·센서 선택 근거)](./architecture/hardware.md)

## Conventions

- [Git (이슈 → 브랜치 → PR → 머지)](./conventions/git.md)
- [Coding](./conventions/coding.md)
- [Version Pinning](./conventions/versions.md)

## Workflows

- [Local Development (Mac / Colab / 보드 역할 분담)](./workflows/local-development.md)
- [Experiment & Measurement](./workflows/experiment.md)
- [Pull Request Writing](./workflows/pull-request-writing.md)
- [Pull Request Template](../.github/pull_request_template.md)

## Decisions

- [Decision Log Guide](./decisions/index.md)
- [결정 사항 (Q-01~09, 문서 불일치)](./decisions/open-questions.md)

## Agent Harness

- [Agent Harness](./agent/index.md)
- [AI 도구별 설정 (Claude Code · Codex · Gemini · Cursor · Copilot 등)](./agent/tools.md)
- [Agent Guide (AGENTS.md)](../AGENTS.md)
- [Task Workflow](../.claude/skills/task-workflow/SKILL.md)
- [Commit Planning Workflow](../.claude/skills/commit-planning-workflow/SKILL.md)
- [PR Prep Workflow](../.claude/skills/pr-prep-workflow/SKILL.md)
- [Experiment Workflow](../.claude/skills/experiment-workflow/SKILL.md)
- [Verify Agent Docs](../.claude/skills/verify-agent-docs/SKILL.md)

## Recipes

- [Board Setup (Orange Pi 초기 세팅)](../recipes/board-setup.md)
- [YOLO → RKNN 변환](../recipes/yolo-to-rknn.md)
- [LLM → RKLLM 변환](../recipes/llm-to-rkllm.md)
- [STT 평가](../recipes/stt-eval.md)
- [새 서비스 추가](../recipes/add-service.md)

## Training

- [training (변환 노트북·스크립트)](../training/README.md)

## Templates

- [Experiment Spec](../templates/experiment.spec.md)
- [Service Spec](../templates/service.spec.md)
- [Issue Templates](../.github/ISSUE_TEMPLATE/)

## Maintenance Rule

- 새 규칙은 먼저 가장 가까운 세부 문서에 추가한다.
- README에는 프로젝트 소개, 빠른 시작, 주요 문서 링크만 둔다.
- agent 실행 지침은 루트 `AGENTS.md`에 둔다 (`CLAUDE.md`는 이를 import).
- 작업 유형별 agent 절차는 `.claude/skills/*/SKILL.md`에 둔다.
- 사람이 따라 하는 반복 절차는 `recipes/*.md`, 작업 전 산출물 형식은 `templates/*.md`에 둔다.
- 문서를 추가·이동하면 이 index를 같이 갱신한다.
