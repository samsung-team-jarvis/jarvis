"""launch.py가 서비스를 띄우고, 로그를 모으고, 순서대로 정리하는지 가짜 서비스로 검사."""

import importlib.util
import io
import pathlib
import subprocess
import sys
import threading

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


def test_stop_kills_service_ignoring_sigterm() -> None:
    launcher = launch.Launcher([spec("stubborn", STUBBORN)], stop_timeout_s=0.5, out=io.StringIO())
    out = run(launcher, seconds=1.0)
    assert "강제 종료" in out
    assert launcher.running[0].proc.returncode is not None


def test_config_loads_modules_in_order() -> None:
    specs, delay = launch.load_config(LAUNCH.with_name("launch.yaml"))
    assert [s.name for s in specs] == ["recorder", "llm_svc", "audio_svc"]
    assert specs[0].argv[-2:] == ["-m", "services.recorder"]
    assert delay > 0


def test_cli_rejects_unknown_service() -> None:
    result = subprocess.run(
        [sys.executable, str(LAUNCH), "--only", "nope"], capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "설정에 없는 서비스" in result.stderr
