"""브랜치 이름, 커밋 메시지, PR 제목·본문이 docs/conventions/git.md 형식을 따르는지 검사한다.

허용 prefix·scope 목록은 git.md의 `## Prefix`, `## Scope` 표에서 읽는다 (문서가 source of truth).

사용:
    python3 scripts/check_conventions.py branch [<branch>]     # 생략 시 현재 브랜치
    python3 scripts/check_conventions.py commit-msg <file>     # git commit-msg 훅
    python3 scripts/check_conventions.py commits <rev-range>   # 예: origin/main..HEAD
    python3 scripts/check_conventions.py pr-title <title>
    python3 scripts/check_conventions.py pr-body <file>
"""

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
GIT_DOC = ROOT / "docs" / "conventions" / "git.md"
DOC_HINT = "형식: docs/conventions/git.md"

# 사람이 만들지 않는 커밋 메시지(머지, 되돌리기)는 형식 검사에서 제외
EXEMPT_COMMIT_RE = re.compile(r"^(Merge |Revert \")")
FORBIDDEN_TRAILER_RE = re.compile(r"^Co-Authored-By:", re.IGNORECASE | re.MULTILINE)
Patterns = dict[str, re.Pattern[str]]

CLOSING_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)


def read_table_keys(section: str) -> list[str]:
    """git.md의 특정 섹션 표에서 첫 열의 `값`들을 읽는다."""
    text = GIT_DOC.read_text(encoding="utf-8")
    match = re.search(rf"^## {section}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(f"git.md에서 '## {section}' 섹션을 찾을 수 없습니다")
    return re.findall(r"^\|\s*`([^`]+)`\s*\|", match.group(1), re.MULTILINE)


def build_patterns() -> Patterns:
    prefixes = "|".join(map(re.escape, read_table_keys("Prefix")))
    scopes = read_table_keys("Scope")
    branch_scopes = "|".join(re.escape(s.replace("/", "-")) for s in scopes)
    commit_scopes = "|".join(map(re.escape, scopes))
    return {
        "branch": re.compile(rf"^({prefixes})/({branch_scopes})/(\d+)-[a-z0-9]+(-[a-z0-9]+)*$"),
        "commit": re.compile(rf"^({prefixes})\(({commit_scopes})\): #(\d+) \S.*$"),
        "pr_title": re.compile(rf"^\[({prefixes.upper()})\]\(({commit_scopes})\): #(\d+) \S.*$"),
    }


def current_branch() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout.strip()


def check_branch(name: str, patterns: Patterns) -> list[str]:
    if name == "main":
        return ["main 브랜치에 직접 push할 수 없습니다. 이슈 브랜치를 만들어 PR로 올려 주세요."]
    if not patterns["branch"].match(name):
        return [
            f"브랜치 이름이 형식에 맞지 않습니다: {name}",
            "  기대: prefix/{scope}/{이슈번호}-work-summary  (예: feat/audio/12-sensevoice-hello)",
        ]
    return []


def check_commit_message(message: str, patterns: Patterns) -> list[str]:
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    subject = lines[0].strip() if lines else ""
    errors = []
    if EXEMPT_COMMIT_RE.match(subject):
        return errors
    if not patterns["commit"].match(subject):
        errors += [
            f"커밋 메시지 첫 줄이 형식에 맞지 않습니다: {subject!r}",
            "  기대: prefix(scope): #{이슈번호} work summary  (예: feat(audio): #12 STT 추가)",
        ]
    if FORBIDDEN_TRAILER_RE.search("\n".join(lines)):
        errors.append("Co-Authored-By 푸터는 넣지 않습니다 (팀 규칙).")
    return errors


def issue_number(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.match(text)
    return match.group(3) if match else None


def cmd_commits(rev_range: str, patterns: Patterns) -> tuple[list[str], list[str]]:
    log = subprocess.run(
        ["git", "log", "--no-merges", "--format=%H%x00%B%x01", rev_range],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    branch_issue = issue_number(patterns["branch"], current_branch())
    errors, warnings = [], []
    for entry in filter(None, (e.strip() for e in log.split("\x01"))):
        sha, message = entry.split("\x00", 1)
        for error in check_commit_message(message, patterns):
            errors.append(f"{sha[:7]}: {error}")
        commit_issue = issue_number(patterns["commit"], message.splitlines()[0])
        if branch_issue and commit_issue and commit_issue != branch_issue:
            warnings.append(f"{sha[:7]}: 커밋 이슈 #{commit_issue} ≠ 브랜치 이슈 #{branch_issue}")
    return errors, warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    patterns = build_patterns()
    command, args = argv[1], argv[2:]
    warnings: list[str] = []

    if command == "branch":
        errors = check_branch(args[0] if args else current_branch(), patterns)
    elif command == "commit-msg":
        message = pathlib.Path(args[0]).read_text(encoding="utf-8")
        errors = check_commit_message(message, patterns)
    elif command == "commits":
        errors, warnings = cmd_commits(args[0], patterns)
    elif command == "pr-title":
        title = args[0] if args else ""
        errors = []
        if not patterns["pr_title"].match(title):
            errors = [
                f"PR 제목이 형식에 맞지 않습니다: {title!r}",
                "  기대: [PREFIX](scope): #{이슈번호} work summary  (예: [FEAT](audio): #12 ...)",
            ]
    elif command == "pr-body":
        body = pathlib.Path(args[0]).read_text(encoding="utf-8")
        errors = [] if CLOSING_RE.search(body) else ["PR 본문에 'Closes #이슈번호'가 없습니다."]
    else:
        print(f"알 수 없는 명령: {command}\n{__doc__}")
        return 2

    for warning in warnings:
        print(f"warning: {warning}")
    if errors:
        print("\n".join(errors))
        print(DOC_HINT)
        return 1
    print(f"OK: {command}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
