"""launch.py가 서비스를 띄우고, 로그를 모으고, 순서대로 정리하는지 가짜 서비스로 검사."""

import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import threading

import pytest
import yaml

LAUNCH = pathlib.Path(__file__).resolve().parents[1] / "launch.py"
_spec = importlib.util.spec_from_file_location("launch", LAUNCH)
launch = importlib.util.module_from_spec(_spec)
sys.modules["launch"] = launch  # dataclass가 모듈을 찾을 수 있게
_spec.loader.exec_module(launch)

SLEEPER = "import signal,sys,time; print('ready', flush=True); time.sleep(30)"
QUICK = "print('done', flush=True)"
FAIL = "import sys; print('boom', flush=True); sys.exit(3)"
STUBBORN = (
    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN);"
    "print('ignoring', flush=True); time.sleep(30)"
)


def spec(name: str, code: str):
    return launch.ServiceSpec(name, [sys.executable, "-u", "-c", code])


def run(launcher, seconds: float = 10.0) -> str:
    stop = threading.Event()
    timer = threading.Timer(seconds, stop.set)
    timer.start()
    launcher.run(stop)
    timer.cancel()
    return launcher.out.getvalue()


def test_until_stops_everything_and_prefixes_logs(tmp_path: pathlib.Path) -> None:
    launcher = launch.Launcher(
        [spec("sleeper", SLEEPER), spec("quick", QUICK)],
        start_delay_s=0.5,
        until="quick",
        log_dir=tmp_path,
        out=io.StringIO(),
    )
    out = run(launcher)
    assert "[sleeper] ready" in out
    assert "[quick] done" in out
    assert "--until quick" in out
    assert all(r.proc.poll() is not None for r in launcher.running)  # 모두 정리됨
    assert (tmp_path / "quick.log").read_text() == "done\n"


def test_restart_failed_service_up_to_limit() -> None:
    launcher = launch.Launcher(
        [spec("fail", FAIL)], restart=True, max_restarts=2, out=io.StringIO()
    )
    out = run(launcher)
    assert out.count("[fail] boom") == 3  # 처음 1번 + 재시작 2번
    assert "재시작 2회" in out
    assert "fail 종료 (code 3)" in out


# Windows의 send_signal(SIGTERM)은 TerminateProcess라 SIGTERM을 무시하는 프로세스가 없다
@pytest.mark.skipif(sys.platform == "win32", reason="Windows는 SIGTERM이 곧 강제 종료")
def test_stop_kills_service_ignoring_sigterm() -> None:
    launcher = launch.Launcher([spec("stubborn", STUBBORN)], stop_timeout_s=0.5, out=io.StringIO())
    out = run(launcher, seconds=1.0)
    assert "강제 종료" in out
    assert launcher.running[0].proc.returncode is not None


def test_config_loads_modules_in_order() -> None:
    specs, delay = launch.load_config(LAUNCH.with_name("launch.yaml"))
    names = [s.name for s in specs]
    assert names == ["recorder", "kitchen_gw", "safety_guard", "llm_svc", "audio_svc"]
    assert specs[0].argv[-2:] == ["-m", "services.recorder"]
    assert delay > 0


def test_cli_rejects_unknown_service() -> None:
    result = subprocess.run(
        [sys.executable, str(LAUNCH), "--only", "nope"],
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},  # Windows 기본 인코딩(cp949)과 무관하게
    )
    assert result.returncode == 1
    assert "설정에 없는 서비스" in result.stderr


def test_config_can_pick_a_python_per_service(tmp_path: pathlib.Path) -> None:
    rel = os.path.relpath(sys.executable, launch.ROOT)  # 저장소 기준 경로로 적는다
    config = tmp_path / "c.yaml"
    config.write_text(
        f"services:\n  - {{name: a, module: m.a}}\n  - {{name: b, module: m.b, python: '{rel}'}}\n",
        encoding="utf-8",
    )
    specs, _ = launch.load_config(config)
    assert specs[0].argv[0] == sys.executable  # 지정하지 않으면 런처의 파이썬
    assert pathlib.Path(specs[1].argv[0]).resolve() == pathlib.Path(sys.executable).resolve()


def test_config_with_missing_python_stops_with_a_message(tmp_path: pathlib.Path) -> None:
    config = tmp_path / "c.yaml"
    config.write_text("services:\n  - {name: llm, module: m, python: .venv-nope/bin/python}\n")
    with pytest.raises(SystemExit, match="llm의 python이 없습니다"):
        launch.load_config(config)


def test_demo_config_runs_the_gguf_llm_in_its_own_env() -> None:
    raw = yaml.safe_load(LAUNCH.with_name("launch_demo.yaml").read_text(encoding="utf-8"))
    items = {s["name"]: s for s in raw["services"]}
    assert list(items)[:2] == ["recorder", "fake_kitchen"]  # 받는 쪽을 먼저
    assert list(items)[-1] == "audio_svc"
    assert items["llm_svc"]["python"] == ".venv-llm/bin/python"
    assert items["llm_svc"]["args"][1].endswith(".gguf")
