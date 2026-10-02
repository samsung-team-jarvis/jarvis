"""AI coding agent 공용 guard hook.

여러 도구의 "셸 명령 실행 전" hook에서 호출한다 (도구별 설정: docs/agent/tools.md).
- 기본 모드: 규칙을 우회하는 git/gh 명령이면 exit 2로 실행을 막고 이유를 stderr로 알린다.
- session-start 모드: git 훅이 설치되지 않았으면 안내를 stdout으로 출력한다 (Claude Code).

도구마다 stdin JSON 모양이 달라서 아래 위치를 차례로 찾는다.
- Claude Code · Codex · Gemini CLI · Copilot(PascalCase): tool_input.command
- Cursor (beforeShellExecution): command
- Windsurf / Devin (pre_run_command): tool_info.command_line
- Antigravity: toolCall.args.CommandLine
- Copilot (camelCase): toolArgs (JSON 문자열 또는 객체).command

규칙 근거: docs/conventions/git.md, docs/agent/index.md
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SEGMENT = r"[^;&|\n]*"  # 같은 명령 조각 안에서만 매칭 (;, &&, |, 줄바꿈으로 끊김)

BLOCKED = [
    (
        re.compile(rf"\bgit\b{SEGMENT}\s--no-verify\b"),
        "--no-verify로 git 훅을 우회할 수 없습니다. 검사 실패 원인을 고치세요.",
    ),
    (
        re.compile(rf"\bgit\s+commit\b{SEGMENT}\s-n\b"),
        "git commit -n(훅 우회)은 금지입니다. 검사 실패 원인을 고치세요.",
    ),
    (
        re.compile(r"core\.hooksPath"),
        "core.hooksPath 변경으로 훅을 우회할 수 없습니다.",
    ),
    (
        re.compile(rf"\bgit\s+push\b{SEGMENT}\s(--force(-with-lease)?|-f)\b"),
        "force push는 금지입니다. 새 커밋으로 고쳐서 push하세요.",
    ),
    (
        re.compile(rf"\bgit\s+push\b{SEGMENT}\s(\S+:)?main\b"),
        "main에 직접 push할 수 없습니다. 이슈 브랜치 → PR로 올리세요.",
    ),
    (
        re.compile(rf"\bgh\s+pr\s+merge\b{SEGMENT}--admin\b"),
        "리뷰 승인 없이 관리자 권한으로 머지할 수 없습니다. 사람이 직접 판단해야 합니다.",
    ),
]

HOOK_FILES = ("pre-commit", "commit-msg", "pre-push")


def dig(data: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def extract_command(event: object) -> str:
    tool_args = dig(event, "toolArgs")
    if isinstance(tool_args, str):
        try:
            tool_args = json.loads(tool_args)
        except json.JSONDecodeError:
            tool_args = None
    candidates = [
        dig(event, "tool_input", "command"),
        dig(event, "command"),
        dig(event, "tool_info", "command_line"),
        dig(event, "toolCall", "args", "CommandLine"),
        dig(tool_args, "command"),
    ]
    return next((c for c in candidates if isinstance(c, str) and c), "")


def guard_bash() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = extract_command(event)
    for pattern, reason in BLOCKED:
        if pattern.search(command):
            print(f"[JARVIS 규칙] {reason} (docs/conventions/git.md)", file=sys.stderr)
            return 2
    return 0


def session_start() -> int:
    hooks_dir = ROOT / ".git" / "hooks"
    missing = [name for name in HOOK_FILES if not (hooks_dir / name).exists()]
    if missing:
        print(f"⚠️ JARVIS: git 훅이 설치되지 않았습니다 ({', '.join(missing)}).")
        print("작업 전에 사용자에게 다음 명령 실행을 안내하세요:")
        print("  python3 scripts/setup.py")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "session-start":
        return session_start()
    return guard_bash()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
