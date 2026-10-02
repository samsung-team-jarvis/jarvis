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
| Claude 팀 설정 | `.claude/settings.json` | 위험 git 명령 거부, 세션 시작 시 훅 설치 여부 경고 |
| Automation | `.github/**`, `.pre-commit-config.yaml`, `.coderabbit.yaml`, `scripts/check_*.py` | PR 자동화, CI, 커밋 전 검사, AI 리뷰 |

## 규칙이 지켜지는 방식

문서(AGENTS.md, skills)는 agent에게 규칙을 알려주지만, agent가 건너뛸 수 있다. 그래서 중요한 규칙은 **도구와 무관한 계층**에서 다시 강제한다.

| 계층 | 누구에게 적용 | 무엇을 막나 |
|---|---|---|
| `AGENTS.md`, skills | 문서를 읽는 agent | 절차 안내 (강제력 없음) |
| `.claude/settings.json` | Claude Code 사용자 | force push, `--no-verify`, main push 명령 |
| pre-commit 훅 | `pre-commit install`한 모든 사람·agent | 형식 틀린 커밋·브랜치, 모델 파일, main push |
| CI (`Conventions`, `CI`) | 모든 PR | 위 규칙 전부 + 문서 링크, ruff |
| 브랜치 보호 | 모든 머지 | CI 실패·리뷰 미승인 PR 머지 |

새 규칙을 만들면 문서에만 쓰지 말고, 가능하면 스크립트·CI 검사도 함께 추가한다.

## Current Shape

```text
AGENTS.md
CLAUDE.md
.claude/
  settings.json
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
- 팀 공통 설정(`.claude/settings.json`)은 안전·컨벤션 강제에 필요한 것만 둔다. 바꿀 때는 이슈 → PR로 하고 PR Point에 영향 범위를 적는다.
- skill·문서를 추가하면 `docs/index.md`와 이 문서의 Current Shape를 갱신하고 [verify-agent-docs](../../.claude/skills/verify-agent-docs/SKILL.md)를 실행한다.
