# AI 도구별 설정

팀원이 어떤 coding agent를 쓰든 같은 지침(`AGENTS.md`)·같은 skill·같은 금지 규칙이 적용되도록 한다.
아래 내용은 2026-10-02에 각 도구 공식 문서로 확인했다. 도구가 업데이트되면 표가 틀릴 수 있으니, 이상하면 이슈를 만들어 갱신한다.

## 한눈에 보기

| 도구 | 지침 (`AGENTS.md`) | skills | 위험 명령 차단 hook | 추가 설정 |
|---|---|---|---|---|
| Claude Code | `CLAUDE.md` → `@AGENTS.md` import | `.claude/skills` | ✅ `.claude/settings.json` | 없음 |
| OpenAI Codex | ✅ 자동 | ✅ `.agents/skills` | ✅ `.codex/hooks.json` | 프로젝트 `.codex/` **신뢰(trust)** 필요 |
| Gemini CLI | `.gemini/settings.json`의 `context.fileName` | ✅ `.agents/skills` | ✅ `.gemini/settings.json` | 없음 |
| Cursor | ✅ 자동 | ✅ `.agents/skills` | △ `.claude/settings.json` hook을 가져옴 | "Third-Party Plugins, Skills, and Other Configs" 켜기 (기본 켜짐) |
| GitHub Copilot | ✅ 자동 (VS Code는 `chat.useAgentsMdFile`) | ✅ `.agents/skills` | △ VS Code `chat.useClaudeHooks` 켜면 `.claude/settings.json` 사용 | 설정 확인 |
| Windsurf (Devin Desktop) | ✅ 자동 | ✅ `.agents/skills` | ✗ (repo 설정 없음) | — |
| Antigravity | ✅ 자동 | ✅ `.agents/skills` | ✗ (repo 설정 없음) | — |

✅ 확인됨 · △ 도구 설정에 따라 동작 · ✗ 이 repo에서 설정하지 않음

**어떤 도구를 쓰든 마지막 방어선은 같다**: git 훅(`pre-commit install`)과 CI `Conventions`·`CI` job은 도구와 무관하게 모든 커밋·PR에 적용된다. hook이 없는 도구를 쓰는 팀원은 반드시 `pre-commit install`을 한다.

## 공통 준비 (모든 도구)

```bash
pip install pre-commit && pre-commit install
```

## 도구별 메모

### Claude Code
- `CLAUDE.md`가 `AGENTS.md`를 import한다. 세션 시작 시 git 훅 미설치를 경고한다.
- `.claude/settings.json`의 `attribution.commit`·`attribution.pr`을 빈 값으로 두어 커밋의 Co-Authored-By와 PR 본문의 "Generated with Claude Code"를 넣지 않는다. 다른 도구는 각자 설정을 끄고, 끄지 않아도 commit-msg 훅·CI가 거부한다.
- 개인 설정은 `.claude/settings.local.json` (git 제외).
- 참고: https://code.claude.com/docs/en/memory.md , https://code.claude.com/docs/en/hooks-guide.md

### OpenAI Codex
- repo 루트부터 현재 디렉터리까지의 `AGENTS.md`를 자동으로 읽는다 (가까운 파일 우선, 기본 32KiB 제한).
- skill은 `.agents/skills`에서 찾는다. 이 repo의 `.agents/skills`는 `.claude/skills`로 가는 심볼릭 링크다.
- `.codex/hooks.json`의 hook은 프로젝트 `.codex/` 레이어를 **신뢰(trust)한 경우에만** 로드된다. 처음 열 때 신뢰 여부를 묻으면 승인한다.
- 개인 설정(모델, 승인 정책)은 `~/.codex/config.toml`에 두고 repo에 커밋하지 않는다.
- 참고: https://learn.chatgpt.com/docs/agent-configuration/agents-md , https://learn.chatgpt.com/docs/build-skills , https://learn.chatgpt.com/docs/hooks

### Gemini CLI
- 기본은 `GEMINI.md`만 읽는다. 이 repo는 `.gemini/settings.json`의 `context.fileName`으로 `AGENTS.md`를 읽게 했다. 별도 `GEMINI.md`는 만들지 않는다 (중복 방지).
- hook 이벤트 이름은 `BeforeTool`, 셸 도구 이름은 `run_shell_command`.
- 참고: https://geminicli.com/docs/cli/gemini-md/ , https://geminicli.com/docs/hooks/reference/

### Cursor
- `AGENTS.md`와 `.agents/skills`를 기본으로 읽는다. `.cursor/rules/`는 쓰지 않는다 (중복 방지).
- Claude Code hook(`.claude/settings.json`)을 가져오는 설정이 기본으로 켜져 있다. `agent_guard.py`는 Cursor의 입력 모양(`command`)도 처리한다. 가져오기 경로의 입력 모양은 공식 문서로 확정하지 못했으므로, git 훅·CI를 함께 믿는다.
- 참고: https://cursor.com/docs/context/rules , https://cursor.com/docs/agent/hooks , https://cursor.com/docs/reference/third-party-hooks

### GitHub Copilot
- `AGENTS.md`를 읽는다. VS Code는 `chat.useAgentsMdFile` 설정이 켜져 있어야 한다.
- VS Code에서 `chat.useClaudeHooks`를 켜면 `.claude/settings.json` hook을 쓴다.
- Copilot coding agent(GitHub 클라우드)가 만든 PR도 CI `Conventions`를 통과해야 머지된다.
- 참고: https://code.visualstudio.com/docs/copilot/customization/custom-instructions , https://docs.github.com/en/copilot/reference/hooks-reference

### Windsurf (Devin Desktop) · Antigravity
- `AGENTS.md`와 `.agents/skills`를 기본으로 읽는다.
- hook 형식이 다르고(입력 모양, 응답 방식) 이 repo에서 검증하지 않았으므로 hook 설정은 두지 않았다. `agent_guard.py`는 두 도구의 입력 모양을 읽을 수 있으니, 필요하면 이슈를 만들어 설정을 추가하고 실제 동작을 확인한다.
- 참고: https://docs.devin.ai/desktop/cascade/hooks , https://antigravity.google/docs/hooks/

## 새 도구를 추가할 때

1. 그 도구가 `AGENTS.md`와 `.agents/skills`를 읽는지 공식 문서로 확인한다. 못 읽으면 import·설정으로 `AGENTS.md`를 가리키게 한다 (지침을 복사하지 않는다).
2. 셸 명령 전 hook이 있으면 `scripts/agent_guard.py`를 호출하도록 설정한다. 입력 모양이 다르면 `extract_command()`와 `scripts/tests/test_agent_guard.py`에 추가한다.
3. hook 명령은 스크립트가 없을 때 통과하도록 감싼다 (`[ ! -f "$f" ] || python3 "$f"`). 경로가 틀리면 Python이 exit 2를 내서 모든 명령이 막히기 때문이다.
4. 이 표를 갱신한다.
