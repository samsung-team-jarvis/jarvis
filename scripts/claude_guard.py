"""Claude Code 팀 공용 hook (.claude/settings.json에서 호출).

- 기본 모드 (PreToolUse, Bash): 규칙을 우회하는 git/gh 명령이면 exit 2로 실행을 막는다.
  stderr 메시지는 Claude에게 전달된다.
- session-start 모드 (SessionStart): git 훅이 설치되지 않았으면 안내를 stdout으로 출력한다.

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


def guard_bash() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = event.get("tool_input", {}).get("command", "")
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
        print("  pip install pre-commit && pre-commit install")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "session-start":
        return session_start()
    return guard_bash()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
