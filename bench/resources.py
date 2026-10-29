"""서비스별 CPU·메모리 측정 (BOARD-08): `-m services.*`로 뜬 프로세스를 1초마다 본다.

python -m bench.resources --duration 60                  # 60초 동안 (서비스는 따로 띄워 둔다)
python -m bench.resources --duration 60 --csv out.csv    # 1초마다의 값

- CPU %: 그 1초 동안 쓴 CPU 시간 ÷ 1초 (100% = 코어 하나). `ps`의 %cpu는 Mac(최근 평균)과
  Linux(시작부터 평균)의 뜻이 달라 쓰지 않고, 누적 CPU 시간(`time`)의 차이로 계산한다.
- 메모리: RSS (실제로 올라와 있는 메모리). 공유 라이브러리·mmap한 모델 파일도 들어간다.
- `ps`만 쓰므로 Mac·Linux(보드) 모두 된다. 서비스가 모두 끝나면 일찍 멈춘다.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

SERVICE = re.compile(r"-m services\.([\w.]+)")


@dataclass(frozen=True)
class Proc:
    pid: int
    service: str
    rss_mb: float
    cpu_s: float  # 시작부터 쓴 CPU 시간


def parse_cputime(text: str) -> float:
    """`ps -o time` → 초. Mac `1:02.34`(분:초.1/100), Linux `01:02:03`·`1-02:03:04`."""
    days, _, rest = text.rpartition("-")
    seconds = 0.0
    for part in rest.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds + (int(days) * 86400 if days else 0)


def service_name(command: str) -> str | None:
    m = SERVICE.search(command)
    return m.group(1).split(".")[-1] if m else None


def parse_ps(text: str) -> list[Proc]:
    """`ps -A -o pid=,rss=,time=,command=` 출력 → 서비스 프로세스만."""
    procs = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        name = service_name(parts[3])
        if name:
            procs.append(Proc(int(parts[0]), name, int(parts[1]) / 1024, parse_cputime(parts[2])))
    return procs


def snapshot() -> list[Proc]:
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,rss=,time=,command="], capture_output=True, text=True, check=True
    )
    return parse_ps(out.stdout)


@dataclass
class Usage:
    cpu: list[float] = field(default_factory=list)
    rss: list[float] = field(default_factory=list)


class Sampler:
    """연속한 두 snapshot의 CPU 시간 차이로 서비스별 CPU %를 낸다."""

    def __init__(self) -> None:
        self.by_service: dict[str, Usage] = defaultdict(Usage)
        self.total_cpu: list[float] = []
        self.total_rss: list[float] = []
        self.rows: list[tuple[float, str, int, float, float]] = []
        self._prev: dict[int, Proc] = {}
        self._prev_t: float | None = None

    def update(self, procs: list[Proc], t: float) -> None:
        if self._prev_t is not None and t > self._prev_t:
            dt = t - self._prev_t
            cpu_sum = rss_sum = 0.0
            for p in procs:
                before = self._prev.get(p.pid)
                if before is None:  # 이번에 처음 본 프로세스는 다음 차례부터
                    continue
                cpu = max(0.0, (p.cpu_s - before.cpu_s) / dt * 100)
                use = self.by_service[p.service]
                use.cpu.append(cpu)
                use.rss.append(p.rss_mb)
                cpu_sum += cpu
                rss_sum += p.rss_mb
                self.rows.append((round(t, 2), p.service, p.pid, round(cpu, 1), round(p.rss_mb, 1)))
            if cpu_sum or rss_sum:
                self.total_cpu.append(cpu_sum)
                self.total_rss.append(rss_sum)
        self._prev = {p.pid: p for p in procs}
        self._prev_t = t

    def report(self) -> str:
        lines = [
            f"CPU %는 코어 하나 = 100% (이 기기 논리 코어 {os.cpu_count()}개), 메모리는 RSS",
            "",
            "| 서비스 | CPU 평균 % | CPU 최대 % | 메모리 최대 MB |",
            "|---|---|---|---|",
        ]
        for name, u in sorted(self.by_service.items(), key=lambda kv: -max(kv[1].rss)):
            lines.append(
                f"| {name} | {sum(u.cpu) / len(u.cpu):.1f} | {max(u.cpu):.1f} | {max(u.rss):.0f} |"
            )
        if self.total_cpu:
            mean = sum(self.total_cpu) / len(self.total_cpu)
            lines.append(
                f"| **합계** ({len(self.total_cpu)}초) | **{mean:.1f}** | "
                f"**{max(self.total_cpu):.1f}** | **{max(self.total_rss):.0f}** |"
            )
        return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="서비스별 CPU·메모리를 1초마다 잰다")
    parser.add_argument("--duration", type=float, default=60.0, help="잴 시간(초)")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--csv", default=None, help="1초마다의 값 (t, service, pid, cpu, rss)")
    args = parser.parse_args()

    sampler = Sampler()
    start = time.monotonic()
    seen = False
    while time.monotonic() - start < args.duration:
        procs = snapshot()
        seen = seen or bool(procs)
        if seen and not procs:
            print("서비스가 모두 끝나 멈춥니다", file=sys.stderr)
            break
        sampler.update(procs, time.monotonic())
        time.sleep(args.interval)
    if not sampler.by_service:
        print("잰 서비스가 없습니다 (`-m services.*` 프로세스를 먼저 띄우세요)", file=sys.stderr)
        return 1
    print(sampler.report())
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "service", "pid", "cpu_pct", "rss_mb"])
            w.writerows(sampler.rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
