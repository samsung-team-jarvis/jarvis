"""CPU 코어 고정 (LLM-19): `--cpus 4-7` → 이 프로세스를 그 코어에서만 돌린다.

RK3588은 빠른 코어(Cortex-A76) 4개와 느린 코어(A55) 4개다. llama.cpp 스레드가 느린 코어에 잡히면
응답이 느려질 수 있어 큰 코어에 고정해 비교한다. 큰 코어 번호는 보드에서 확인한다 (확인 필요:
`lscpu`, `cat /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq`).

리눅스 `os.sched_setaffinity`를 쓴다. 맥·윈도에는 없어서 경고만 하고 넘어간다.
스레드를 만들기 전에(모델을 읽기 전에) 불러야 한다 — 새 스레드는 만든 스레드의 설정을 물려받는다.
"""

from __future__ import annotations

import os


def parse_cpus(text: str) -> set[int]:
    """ "4-7" · "4,5,6,7" · "0,4-7" → {코어 번호}."""
    cpus: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        lo, sep, hi = part.partition("-")
        if not lo.isdigit() or (sep and not hi.isdigit()):
            raise ValueError(f"코어 번호 형식이 아닙니다: {text!r} (예: 4-7, 4,5,6,7)")
        start, end = int(lo), int(hi) if sep else int(lo)
        if end < start:
            raise ValueError(f"범위가 거꾸로입니다: {part!r}")
        cpus.update(range(start, end + 1))
    if not cpus:
        raise ValueError("코어를 하나 이상 적어 주세요")
    return cpus


def pin(text: str | None) -> set[int] | None:
    """코어를 고정하고, 고정한 코어를 돌려준다. 고정하지 못하면 이유를 출력하고 None."""
    if not text:
        return None
    cpus = parse_cpus(text)
    if not hasattr(os, "sched_setaffinity"):
        print(f"경고: 이 OS에서는 코어 고정을 할 수 없어 --cpus {text}를 무시합니다 (리눅스 전용)")
        return None
    available = os.sched_getaffinity(0)
    missing = cpus - available
    if missing:
        raise ValueError(f"없는 코어: {sorted(missing)} (쓸 수 있는 코어: {sorted(available)})")
    os.sched_setaffinity(0, cpus)
    return cpus
