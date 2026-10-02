"""JARVIS 개발 환경 원커맨드 세팅 (macOS · Linux · Windows).

사용: python3 scripts/setup.py          (Windows: py scripts\\setup.py)

1. Python 버전 확인 (3.10 이상)
2. .venv 가상환경 생성 (없을 때만)
3. 개발 도구 설치 (requirements-dev.txt)
4. git 훅 설치 (pre-commit · commit-msg · pre-push)
5. git 사용자 정보 확인
6. 빠른 검사 실행 (스크립트 테스트, 문서 링크, ruff)

여러 번 실행해도 안전하다.
"""

import os
import pathlib
import subprocess
import sys
import venv

ROOT = pathlib.Path(__file__).resolve().parent.parent
VENV_DIR = ROOT / ".venv"
MIN_PYTHON = (3, 10)


def venv_python() -> pathlib.Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def step(title: str) -> None:
    print(f"\n▶ {title}")


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=ROOT, check=check, text=True, capture_output=not check)


def git_config(key: str) -> str:
    result = subprocess.run(["git", "config", key], cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # 하위 명령 출력과 순서가 섞이지 않게
    step("Python 버전 확인")
    current = sys.version.split()[0]
    if sys.version_info < MIN_PYTHON:
        print(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 이상이 필요합니다 (현재 {current}).")
        return 1
    print(f"Python {current}")

    step("가상환경 (.venv)")
    if venv_python().exists():
        print("이미 있음")
    else:
        venv.create(VENV_DIR, with_pip=True)
        print("생성함")
    py = str(venv_python())

    step("개발 도구 설치 (requirements-dev.txt)")
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"])
    run([py, "-m", "pip", "install", "-q", "-r", "requirements-dev.txt"])
    print("완료")

    step("git 훅 설치")
    run([py, "-m", "pre_commit", "install"])

    step("git 사용자 정보")
    name, email = git_config("user.name"), git_config("user.email")
    if not name or not email:
        print("⚠️ git 사용자 정보가 없습니다. 아래를 실행하세요 (이메일은 GitHub 계정 이메일):")
        print('  git config --global user.name "이름"')
        print('  git config --global user.email "GitHub 계정 이메일"')
    else:
        print(f"{name} <{email}>")
        print("이 이메일이 GitHub 계정에 등록된 이메일이어야 커밋 기록이 본인 계정에 남습니다.")

    step("빠른 검사")
    checks = [
        ("스크립트 테스트", [py, "-m", "pytest", "scripts/tests", "-q"]),
        ("문서 링크", [py, "scripts/check_doc_links.py"]),
        ("ruff", [py, "-m", "ruff", "check", "."]),
    ]
    failed = []
    for label, args in checks:
        ok = run(args, check=False).returncode == 0
        print(f"{'✅' if ok else '❌'} {label}")
        if not ok:
            failed.append(label)

    activate = r".venv\Scripts\activate" if os.name == "nt" else "source .venv/bin/activate"
    print("\n완료. 작업할 때는 가상환경을 켜세요:")
    print(f"  {activate}")
    print("다음 단계: docs/onboarding.md 체크리스트")
    if failed:
        print(f"\n⚠️ 실패한 검사: {', '.join(failed)} — 직접 실행해서 원인을 확인하세요.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
