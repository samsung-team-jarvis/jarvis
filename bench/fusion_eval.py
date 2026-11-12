"""상황 인식 평가 (FUS-07): simulator 시나리오 → 1초마다 판정 State vs 정답 State.

python -m bench.fusion_eval --judge temp --split val                 # 온도만 Baseline
python -m bench.fusion_eval --judge person --split val --per-scenario
python -m bench.fusion_eval --judge temp --judge person --split test  # 나란히 (test는 비교에만)

판정기(Judge)는 시나리오의 메시지를 시간 순으로 받고(`update`), 1초마다 지금 State를
답한다(`state`). 버스 없이 `services.simulator.runner.build_events`의 메시지를 그대로 넣는다.
상태는 `update`에서만 바꾸고 `state`는 읽기만 한다 (부르는 횟수·시점에 따라 답이 달라지지 않게).
FUS-08 State Machine(`fusion`)도 같은 방식으로 평가한다.

지표 (METRICS §State F1·위험 미탐율, 정의: #140):
- State F1: 1초마다 비교, State별 F1을 모든 시나리오의 초를 모아 계산하고 평균(macro).
  정답과 예측 어디에도 없는 State는 평균에서 뺀다.
- 위험 미탐율: 정답의 위험 구간(`DANGER`·`UNATTENDED`가 이어진 구간, State가 바뀌면 다른 구간)
  동안 한 번도 위험 상태(Safety Guard가 가열을 막는 `UNATTENDED`·`DANGER`·`SAFE_STOP`)로 판정하지
  못한 구간의 비율. 감지한 구간은 구간 시작부터 처음 위험 판정까지의 초(감지 지연).
- 위험 오탐: 정답이 위험 상태가 아닌 초 중 위험 상태로 판정한 초의 비율 (참고).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from collections import Counter
from typing import Any, Protocol

from services.fusion_svc.state_machine import StateMachine
from services.safety_guard.rules import RISKY_STATES, STATES
from services.simulator.runner import build_events
from services.simulator.scenario import Scenario, expected_at, load

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCENARIO_DIR = ROOT / "services/simulator/scenarios"
SPLIT_FILE = ROOT / "data/fusion/split_v1.json"

DANGER_STATES = frozenset({"DANGER", "UNATTENDED"})  # 정답에서 위험 구간으로 세는 State

# 판정 기준 (docs/decisions/2026-11-09-state-rules.md) — Baseline도 같은 값을 쓴다
DANGER_C, DANGER_EXIT_C = 240.0, 230.0
COOK_C = 100.0
UNATTENDED_S = 30.0
RISE_C = 0.5  # 온도만 Baseline: 직전 값보다 이만큼 오르면 "데워지는 중"


class Judge(Protocol):
    def update(self, t: float, topic: str, payload: dict[str, Any]) -> None: ...
    def state(self, t: float) -> str: ...


class TemperatureOnly:
    """온도만 본다 (`sensor/reading`). 가열 장치가 켜졌는지·사람이 있는지는 모른다.

    가장 뜨거운 장치가 240°C 이상이면 DANGER(230°C 아래에서 해제), 100°C 이상이면 COOKING,
    아래인데 데워지는 장치가 있으면 PREHEAT, 아니면 IDLE. UNATTENDED·SAFE_STOP은 낼 수 없다.
    """

    def __init__(self) -> None:
        self.temps: dict[str, float] = {}
        self.rising: dict[str, bool] = {}
        self.danger = False

    def update(self, t: float, topic: str, payload: dict[str, Any]) -> None:
        if topic != "sensor/reading":
            return
        device, temp = payload["device_id"], float(payload["temperature_c"])
        previous = self.temps.get(device)
        self.rising[device] = previous is not None and temp - previous >= RISE_C
        self.temps[device] = temp
        # DANGER 해제 기준(230°C)은 온도가 들어올 때 갱신한다 — state()는 읽기만 한다
        hottest = max(self.temps.values())
        self.danger = hottest >= DANGER_C or (self.danger and hottest >= DANGER_EXIT_C)

    def state(self, t: float) -> str:
        hottest = max(self.temps.values(), default=0.0)
        if self.danger:
            return "DANGER"
        if hottest >= COOK_C:
            return "COOKING"
        if any(self.rising.values()):
            return "PREHEAT"
        return "IDLE"


class PersonOnly:
    """사람 감지만 본다 (`vision/objects`의 `person`). 가열 장치·온도는 모른다.

    사람이 30초 연속 보이지 않으면 UNATTENDED, 아니면 IDLE (조리 중인지 알 수 없다).
    """

    def __init__(self) -> None:
        self.absent_since: float | None = None

    def update(self, t: float, topic: str, payload: dict[str, Any]) -> None:
        if topic != "vision/objects":
            return
        person = any(o["cls"] == "person" for o in payload["objects"])
        if person:
            self.absent_since = None
        elif self.absent_since is None:
            self.absent_since = t

    def state(self, t: float) -> str:
        if self.absent_since is not None and t - self.absent_since >= UNATTENDED_S:
            return "UNATTENDED"
        return "IDLE"


JUDGES = {"temp": TemperatureOnly, "person": PersonOnly, "fusion": StateMachine}


@dataclasses.dataclass(frozen=True)
class Tick:
    scenario: str
    t: int
    truth: str
    pred: str


def run(sc: Scenario, judge: Judge) -> list[Tick]:
    """시나리오를 판정기에 흘리고 매 초(0초부터) 정답과 예측을 모은다."""
    events = build_events(sc)
    ticks, i = [], 0
    for t in range(int(sc.duration_s) + 1):
        while i < len(events) and events[i].t <= t:
            judge.update(events[i].t, events[i].type, events[i].payload_fn())
            i += 1
        truth = expected_at(sc, t)
        if truth is None:
            raise ValueError(f"{sc.name}: 정답 State(expected)가 없습니다")
        ticks.append(Tick(sc.name, t, truth, judge.state(t)))
    return ticks


def state_f1(ticks: list[Tick]) -> tuple[float, dict[str, dict[str, float]]]:
    """macro F1과 State별 {precision, recall, f1, support}."""
    per: dict[str, dict[str, float]] = {}
    for s in STATES:
        tp = sum(1 for k in ticks if k.truth == s and k.pred == s)
        fp = sum(1 for k in ticks if k.truth != s and k.pred == s)
        fn = sum(1 for k in ticks if k.truth == s and k.pred != s)
        if tp + fp + fn == 0:
            continue  # 정답·예측 어디에도 없음
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        per[s] = {"precision": p, "recall": r, "f1": f1, "support": tp + fn}
    macro = sum(v["f1"] for v in per.values()) / len(per) if per else 0.0
    return macro, per


@dataclasses.dataclass(frozen=True)
class Segment:
    scenario: str
    state: str
    start: int
    end: int  # 마지막 초 (포함)
    delay: int | None  # 처음 위험 판정까지의 초, 놓쳤으면 None


def danger_segments(ticks: list[Tick]) -> list[Segment]:
    """정답의 위험 구간마다 감지 여부와 지연 (ticks는 한 시나리오씩 시간 순)."""
    segments: list[Segment] = []
    run_start: int | None = None
    for i, k in enumerate(ticks):
        starts = k.truth in DANGER_STATES and (
            i == 0 or ticks[i - 1].scenario != k.scenario or ticks[i - 1].truth != k.truth
        )
        if starts:
            run_start = i
        last = i + 1 == len(ticks) or ticks[i + 1].scenario != k.scenario
        ends = run_start is not None and (last or ticks[i + 1].truth != k.truth)
        if ends:
            part = ticks[run_start : i + 1]
            hit = next((x.t - part[0].t for x in part if x.pred in RISKY_STATES), None)
            segments.append(Segment(k.scenario, k.truth, part[0].t, k.t, hit))
            run_start = None
    return segments


def summarize(ticks: list[Tick]) -> dict[str, Any]:
    macro, per = state_f1(ticks)
    segments = danger_segments(ticks)
    missed = [s for s in segments if s.delay is None]
    delays = [s.delay for s in segments if s.delay is not None]
    safe = [k for k in ticks if k.truth not in RISKY_STATES]
    false_alarm = sum(1 for k in safe if k.pred in RISKY_STATES)
    return {
        "ticks": len(ticks),
        "accuracy": sum(k.truth == k.pred for k in ticks) / len(ticks),
        "macro_f1": macro,
        "per_state": per,
        "segments": len(segments),
        "missed": len(missed),
        "miss_rate": len(missed) / len(segments) if segments else 0.0,
        "missed_list": [f"{s.scenario}:{s.state}@{s.start}" for s in missed],
        "delay_mean": sum(delays) / len(delays) if delays else None,
        "delay_max": max(delays) if delays else None,
        "false_alarm_rate": false_alarm / len(safe) if safe else 0.0,
    }


def split_names(split: str) -> list[str]:
    data = json.loads(SPLIT_FILE.read_text(encoding="utf-8"))
    if split == "all":
        return sorted(data["val"] + data["test"])
    return data[split]


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def report(name: str, result: dict[str, Any]) -> str:
    lines = [
        f"[{name}] {result['ticks']}초 · 정확도 {_pct(result['accuracy'])} · "
        f"State F1(macro) {result['macro_f1']:.3f}",
        "  State별 F1: "
        + ", ".join(
            f"{s} {v['f1']:.2f} (P {v['precision']:.2f} R {v['recall']:.2f}, n={v['support']:.0f})"
            for s, v in result["per_state"].items()
        ),
        f"  위험 미탐율 {_pct(result['miss_rate'])} ({result['missed']}/{result['segments']} 구간)"
        + (
            f" · 감지 지연 평균 {result['delay_mean']:.1f}초 · 최대 {result['delay_max']}초"
            if result["delay_mean"] is not None
            else ""
        )
        + f" · 위험 오탐 {_pct(result['false_alarm_rate'])}",
    ]
    if result["missed_list"]:
        lines.append("  놓친 구간: " + ", ".join(result["missed_list"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="상황 인식 판정기를 시나리오 정답과 비교한다")
    parser.add_argument("--judge", action="append", choices=sorted(JUDGES), required=True)
    parser.add_argument("--split", choices=("val", "test", "all"), default="val")
    parser.add_argument("--per-scenario", action="store_true", help="시나리오마다 따로 출력")
    args = parser.parse_args(argv)

    scenarios = [load(SCENARIO_DIR / f"{n}.yaml") for n in split_names(args.split)]
    print(f"split={args.split} 시나리오 {len(scenarios)}개")
    for name in args.judge:
        ticks: list[Tick] = []
        for sc in scenarios:
            part = run(sc, JUDGES[name]())
            ticks += part
            if args.per_scenario:
                wrong = Counter((k.truth, k.pred) for k in part if k.truth != k.pred)
                top = ", ".join(f"{a}→{b} {n}초" for (a, b), n in wrong.most_common(3))
                print(f"  {sc.name:26} 정확도 {_pct(summarize(part)['accuracy'])}  {top}")
        print(report(name, summarize(ticks)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
