"""Markdown 문서의 상대 경로 링크가 실제 파일을 가리키는지 검사한다.

사용: python scripts/check_doc_links.py
깨진 링크가 있으면 목록을 출력하고 종료 코드 1을 반환한다.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", ".agents"}
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)


def iter_markdown_files() -> list[pathlib.Path]:
    return [
        path
        for path in ROOT.rglob("*.md")
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts)
    ]


def broken_links(md_file: pathlib.Path) -> list[str]:
    text = CODE_RE.sub("", md_file.read_text(encoding="utf-8"))
    broken = []
    for target in LINK_RE.findall(text):
        target = target.split("#", 1)[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        if not (md_file.parent / target).exists():
            broken.append(target)
    return broken


def main() -> int:
    failures = []
    for md_file in iter_markdown_files():
        for target in broken_links(md_file):
            failures.append(f"{md_file.relative_to(ROOT)}: {target}")

    if failures:
        print("Broken links:")
        print("\n".join(failures))
        return 1

    print("OK: no broken relative links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
