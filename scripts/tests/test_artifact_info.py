import hashlib
import os
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "artifact_info.py"
UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # Windows 기본 인코딩(cp949)과 무관하게


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, encoding="utf-8", env=UTF8_ENV
    )


def test_prints_registry_row(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "vision_kitchen_v1_i8.rknn"
    f.write_bytes(b"x" * 2048)
    expected = hashlib.sha256(b"x" * 2048).hexdigest()[:12]
    out = run(str(f)).stdout
    assert f"| `vision_kitchen_v1_i8.rknn` | 2.0 KB | `{expected}` |" in out


def test_check_detects_match_and_mismatch(tmp_path: pathlib.Path) -> None:
    f = tmp_path / "a.bin"
    f.write_bytes(b"hello")
    good = hashlib.sha256(b"hello").hexdigest()[:12]
    assert run("--check", str(f), good).returncode == 0
    assert run("--check", str(f), "000000000000").returncode == 1
