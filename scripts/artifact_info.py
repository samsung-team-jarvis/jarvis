"""산출물 파일의 크기·sha256을 docs/artifacts.md 등록부 형식으로 출력한다.

공용 저장소 없이 메신저·USB로 파일을 주고받으므로, 받은 쪽에서 같은 명령을 실행해
sha256 앞 12자리가 등록부와 같은지 보면 전달 중 깨지지 않았는지 확인할 수 있다.

사용:
    python3 scripts/artifact_info.py <파일> [<파일> ...]
    python3 scripts/artifact_info.py --check <파일> <sha256 앞 12자리>
"""

import argparse
import hashlib
import pathlib
import sys

SHORT = 12


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1000  # 십진 단위 (ls·변환 로그와 같은 MB)
    return f"{n:.1f} GB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=pathlib.Path)
    parser.add_argument("--check", nargs=2, metavar=("FILE", "SHA12"))
    args = parser.parse_args()

    if args.check:
        path, expected = pathlib.Path(args.check[0]), args.check[1].lower()
        actual = sha256(path)[:SHORT]
        ok = actual == expected[:SHORT]
        print(f"{'OK' if ok else 'MISMATCH'}: {path.name} sha256={actual} (등록부: {expected})")
        return 0 if ok else 1

    if not args.files:
        parser.print_usage()
        return 2
    print("| 파일 | 크기 | sha256(앞 12) |")
    print("|---|---|---|")
    for path in args.files:
        print(f"| `{path.name}` | {human_size(path.stat().st_size)} | `{sha256(path)[:SHORT]}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
