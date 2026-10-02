# Agent Harness

Claude Code, Codex 등 coding agent가 이 repo에서 읽는 문서·skill·설정의 역할을 정리한다.

## Layer Model

| Layer | Source of truth | Role |
|---|---|---|
| Entry point | `AGENTS.md` | agent가 먼저 읽는 짧은 라우팅 허브 (Codex 자동 로드) |
| Claude entry | `CLAUDE.md` | `@AGENTS.md` import + Claude Code 전용 메모 (Claude Code 자동 로드) |
| Project guide | `README.md`, `docs/index.md` | 사람이 보는 진입점 |
| Detailed docs | `docs/**` | 아키텍처, 컨벤션, workflow, 결정 |
| Repeatable flow | `recipes/**`, `templates/**` | 반복 절차, 작업 전 산출물 형식 |
| Agent workflow | `.claude/skills/*/SKILL.md` | 작업 유형별 agent 실행 절차 |
| Codex skill path | `.agents/skills` → `.claude/skills` 심볼릭 링크 | Codex 사용자도 같은 skill을 읽게 함 |
| Automation | `.github/**`, `.pre-commit-config.yaml`, `.coderabbit.yaml` | PR 자동화, CI, 커밋 전 검사, AI 리뷰 |

## Current Shape

```text
AGENTS.md
CLAUDE.md
.claude/
  skills/
    task-workflow/SKILL.md
    commit-planning-workflow/SKILL.md
    pr-prep-workflow/SKILL.md
    experiment-workflow/SKILL.md
    verify-agent-docs/SKILL.md
.agents/skills -> ../.claude/skills
.github/
docs/
recipes/
templates/
```

## Maintenance Rule

- `AGENTS.md`는 어디를 먼저 읽을지 알려주는 짧은 허브로 유지한다. 상세 규칙을 복사하지 않는다.
- skill은 `.claude/skills/<name>/SKILL.md` 하나에만 둔다. frontmatter에 `name`, `description` 필수. 중첩 그룹 금지.
- 개인 선호 설정(모델, 권한, 개인 hook)은 repo에 커밋하지 않는다 (`.claude/settings.local.json`, 사용자 전역 설정).
- 팀 공통 hook·설정은 팀 합의 후 별도 이슈로 추가한다.
- skill·문서를 추가하면 `docs/index.md`와 이 문서의 Current Shape를 갱신하고 [verify-agent-docs](../../.claude/skills/verify-agent-docs/SKILL.md)를 실행한다.
