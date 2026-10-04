"""agent_guard.py가 도구별 입력 모양에서 규칙 우회 명령을 막고 일반 명령은 통과시키는지 검사."""

import json
import pathlib
import subprocess
import sys

import pytest

GUARD = pathlib.Path(__file__).resolve().parents[1] / "agent_guard.py"


def run_guard(event: object) -> int:
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(event),
        capture_output=True,
        encoding="utf-8",
        errors="replace",  # 출력은 안 본다. Windows(cp949)에서 읽기 오류만 막는다
    )
    return result.returncode


BLOCKED_COMMANDS = [
    'git commit --no-verify -m "x"',
    'git commit -n -m "x"',
    "git -c core.hooksPath=/dev/null commit -m x",
    "git push --force origin feat/a/1-x",
    "git push -f",
    "git push --force-with-lease",
    "git push origin main",
    "git push origin HEAD:main",
    "gh pr merge 3 --merge --admin",
    "cd x && git push --no-verify",
]

ALLOWED_COMMANDS = [
    'git commit -m "feat(audio): #12 x"',
    'git commit -am "fix(ble): #4 y"',
    "git push -u origin feat/audio/12-main-loop",
    "git checkout main",
    "git pull origin main",
    "gh pr merge 3 --merge",
    "ls -n",
]


def shapes(command: str) -> dict[str, object]:
    """도구별 hook stdin 모양 (scripts/agent_guard.py docstring 참고)."""
    return {
        "claude": {"tool_name": "Bash", "tool_input": {"command": command}},
        "gemini": {"tool_name": "run_shell_command", "tool_input": {"command": command}},
        "cursor": {"command": command, "cwd": "/repo"},
        "windsurf": {"tool_info": {"command_line": command}},
        "antigravity": {"toolCall": {"name": "run_command", "args": {"CommandLine": command}}},
        "copilot_str": {"toolName": "bash", "toolArgs": json.dumps({"command": command})},
        "copilot_obj": {"toolName": "bash", "toolArgs": {"command": command}},
    }


@pytest.mark.parametrize("command", BLOCKED_COMMANDS)
@pytest.mark.parametrize("tool", list(shapes("").keys()))
def test_blocks_rule_bypass(tool: str, command: str) -> None:
    assert run_guard(shapes(command)[tool]) == 2


@pytest.mark.parametrize("command", ALLOWED_COMMANDS)
@pytest.mark.parametrize("tool", ["claude", "cursor", "windsurf"])
def test_allows_normal_commands(tool: str, command: str) -> None:
    assert run_guard(shapes(command)[tool]) == 0


@pytest.mark.parametrize("event", [[], {}, {"tool_input": None}, {"toolArgs": "not json"}])
def test_unknown_input_is_not_blocked(event: object) -> None:
    assert run_guard(event) == 0
