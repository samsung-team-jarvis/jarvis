"""서비스 일괄 기동·종료 (BOARD-07). Mac·보드 공통.

python3 scripts/launch.py              # launch.yaml의 서비스 모두 (Ctrl+C로 모두 종료)
python3 scripts/launch.py --only recorder,llm_svc
python3 scripts/launch.py --arg audio_svc="--input data/stt/cmds.wav --realtime" --until audio_svc
python3 scripts/launch.py --bus mqtt://localhost:1883 --log-dir data/logs --restart

- 로그는 `[서비스]` 접두어로 한 화면에 모은다. --log-dir를 주면 서비스별 파일로도 남긴다.
- 종료: Ctrl+C·SIGTERM → 모든 서비스에 SIGTERM (뒤에 띄운 것부터).
  stop_timeout 안에 안 끝나면 SIGKILL.
- --until <서비스>: 그 서비스가 끝나면 나머지도 정리한다 (wav 재생 측정 자동화).
- --restart: 0이 아닌 코드로 죽은 서비스를 다시 띄운다 (최대 --max-restarts회).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import os
import pathlib
import shlex
import signal
import subprocess
import sys
import threading
import time
from typing import TextIO

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = pathlib.Path(__file__).with_name("launch.yaml")


@dataclasses.dataclass
class ServiceSpec:
    name: str
    argv: list[str]


@dataclasses.dataclass
class Running:
    spec: ServiceSpec
    proc: subprocess.Popen
    restarts: int = 0
    reported: bool = False


def load_config(path: pathlib.Path) -> tuple[list[ServiceSpec], float]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    specs = []
    for item in raw.get("services", []):
        name, module = item["name"], item["module"]
        argv = [sys.executable, "-u", "-m", module, *[str(a) for a in item.get("args", [])]]
        specs.append(ServiceSpec(name, argv))
    return specs, float(raw.get("start_delay_s", 1.0))


class Launcher:
    def __init__(
        self,
        specs: list[ServiceSpec],
        env: dict[str, str] | None = None,
        start_delay_s: float = 1.0,
        stop_timeout_s: float = 5.0,
        restart: bool = False,
        max_restarts: int = 3,
        until: str | None = None,
        log_dir: pathlib.Path | None = None,
        out: TextIO = sys.stdout,
    ) -> None:
        self.specs = specs
        self.env = env
        self.start_delay_s = start_delay_s
        self.stop_timeout_s = stop_timeout_s
        self.restart = restart
        self.max_restarts = max_restarts
        self.until = until
        self.log_dir = log_dir
        self.out = out
        self.running: list[Running] = []
        self._out_lock = threading.Lock()
        self._pumps: list[threading.Thread] = []

    def say(self, name: str, line: str) -> None:
        with self._out_lock:
            self.out.write(f"[{name}] {line}\n")
            self.out.flush()

    def _spawn(self, spec: ServiceSpec) -> subprocess.Popen:
        proc = subprocess.Popen(
            spec.argv,
            cwd=ROOT,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,  # Ctrl+C는 런처만 받고, 종료 신호는 런처가 순서대로 보낸다
        )
        log = None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log = (self.log_dir / f"{spec.name}.log").open("a", encoding="utf-8")

        def pump() -> None:
            for line in proc.stdout:
                line = line.rstrip("\n")
                self.say(spec.name, line)
                if log:
                    log.write(line + "\n")
                    log.flush()
            if log:
                log.close()

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        self._pumps.append(t)
        return proc

    def start(self) -> None:
        for i, spec in enumerate(self.specs):
            if i:
                time.sleep(self.start_delay_s)
            self.running.append(Running(spec, self._spawn(spec)))
            self.say("launcher", f"{spec.name} 시작 (pid {self.running[-1].proc.pid})")

    def poll(self) -> bool:
        """죽은 서비스를 처리한다. 런처를 끝내야 하면 False."""
        for r in self.running:
            code = r.proc.poll()
            if code is None or r.reported:
                continue
            if code != 0 and self.restart and r.restarts < self.max_restarts:
                r.restarts += 1
                self.say(
                    "launcher", f"{r.spec.name} 비정상 종료(code {code}) → 재시작 {r.restarts}회"
                )
                r.proc = self._spawn(r.spec)
                continue
            r.reported = True
            self.say("launcher", f"{r.spec.name} 종료 (code {code})")
            if r.spec.name == self.until:
                self.say("launcher", f"--until {self.until}: 나머지를 정리합니다")
                return False
        return any(r.proc.poll() is None for r in self.running)

    def stop(self) -> None:
        alive = [r for r in reversed(self.running) if r.proc.poll() is None]
        for r in alive:
            r.proc.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + self.stop_timeout_s
        for r in alive:
            try:
                r.proc.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                self.say(
                    "launcher",
                    f"{r.spec.name}이(가) {self.stop_timeout_s:g}초 안에 안 끝나 강제 종료",
                )
                r.proc.kill()
                r.proc.wait()
        for t in self._pumps:
            t.join(timeout=1)
        for r in self.running:
            if not r.reported:
                r.reported = True
                self.say("launcher", f"{r.spec.name} 종료 (code {r.proc.returncode})")

    def run(self, stop: threading.Event) -> None:
        self.start()
        try:
            while not stop.wait(0.2):
                if not self.poll():
                    break
        finally:
            self.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="서비스를 한 번에 띄우고 한 번에 정리한다")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--only", default=None, help="띄울 서비스 이름 (쉼표로 구분)")
    parser.add_argument(
        "--arg", action="append", default=[], metavar='NAME="ARGS"', help="서비스별 추가 인자"
    )
    parser.add_argument("--bus", default=None, help="모든 서비스의 JARVIS_BUS")
    parser.add_argument("--until", default=None, help="이 서비스가 끝나면 전체 종료")
    parser.add_argument("--restart", action="store_true", help="비정상 종료 시 재시작")
    parser.add_argument("--max-restarts", type=int, default=3)
    parser.add_argument("--stop-timeout", type=float, default=5.0)
    parser.add_argument(
        "--log-dir", type=pathlib.Path, default=None, help="서비스별 로그 파일 폴더"
    )
    args = parser.parse_args()

    specs, delay = load_config(args.config)
    names = [s.name for s in specs]
    if args.only:
        wanted = [n.strip() for n in args.only.split(",")]
        if unknown := set(wanted) - set(names):
            print(f"설정에 없는 서비스: {sorted(unknown)} (있는 것: {names})", file=sys.stderr)
            return 1
        specs = [s for s in specs if s.name in wanted]
    for item in args.arg:
        name, sep, extra = item.partition("=")
        spec = next((s for s in specs if s.name == name), None)
        if not sep or spec is None:
            print(f'--arg 형식은 NAME="ARGS" (NAME은 띄울 서비스): {item!r}', file=sys.stderr)
            return 1
        spec.argv += shlex.split(extra)
    if args.until and args.until not in [s.name for s in specs]:
        print(f"--until 서비스가 목록에 없음: {args.until}", file=sys.stderr)
        return 1

    env = dict(os.environ)
    if args.bus:
        env["JARVIS_BUS"] = args.bus
    log_dir = (
        args.log_dir / datetime.datetime.now().strftime("%Y%m%d_%H%M%S") if args.log_dir else None
    )

    launcher = Launcher(
        specs,
        env=env,
        start_delay_s=delay,
        stop_timeout_s=args.stop_timeout,
        restart=args.restart,
        max_restarts=args.max_restarts,
        until=args.until,
        log_dir=log_dir,
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    launcher.run(stop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
