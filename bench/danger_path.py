"""위험 감지 → 차단 지연 (FUS-09): recorder 녹화에서 자동 차단 한 건마다 구간별 지연(ms).

python -m bench.danger_path data/sessions/                      # 폴더 안의 녹화를 모두 합쳐 본다
python -m bench.danger_path data/sessions/a.jsonl data/sessions/b.jsonl

서비스마다 세션이 달라서(온도는 kitchen_gw, 판정은 fusion_svc) 여러 파일을 `mono` 순으로 합친다.
`mono`는 각 서비스가 발행할 때 찍은 보드의 단조 시계다 (bench/latency.py와 같은 전제).

  과열: sensor/reading(그 장치가 240°C 이상이 된 첫 값) → fusion/state → guard/decision
        → control/command → control/result
  방치: fusion/state(사람 없음 60초가 된 판정) → guard/decision → control/command → control/result
        (방치 판정 뒤 유예 30초는 정책이라 지연에 넣지 않고 따로 보인다)
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys
from collections.abc import Iterable

from common.messages import Envelope
from services.fusion_svc.state_machine import DANGER_C, UNATTENDED_S
from services.recorder.store import read_session
from services.safety_guard.auto_stop import REASON_PREFIX, STOP_ABSENT_S

STAGE_ORDER = {
    t: i
    for i, t in enumerate(
        ["sensor/reading", "fusion/state", "guard/decision", "control/command", "control/result"]
    )
}
SEGMENTS = [
    ("to_fusion", "위험 온도 sensor/reading → fusion/state (과열만)"),
    ("to_guard", "fusion/state → guard/decision (자동 차단 판정)"),
    ("to_command", "guard/decision → control/command"),
    ("to_ack", "control/command → control/result (가상 주방 왕복)"),
    ("e2e", "감지 → control/result (과열: 위험 온도 수신부터, 방치: 판정부터)"),
]


@dataclasses.dataclass
class Stop:
    kind: str  # 과열 | 방치
    target: str
    decision: Envelope
    trigger: Envelope | None = None  # 판정의 근거가 된 fusion/state
    reading: Envelope | None = None  # 과열: 240°C 이상이 된 첫 온도
    command: Envelope | None = None
    result: Envelope | None = None
    unattended_s: float | None = None  # 방치: 방치 판정(30초) 뒤 차단까지 (유예)

    def segments(self) -> dict[str, float | None]:
        def gap(a: Envelope | None, b: Envelope | None) -> float | None:
            return round((b.mono - a.mono) * 1000, 3) if a and b else None

        start = self.reading if self.kind == "과열" else self.trigger
        return {
            "to_fusion": gap(self.reading, self.trigger),
            "to_guard": gap(self.trigger, self.decision),
            "to_command": gap(self.decision, self.command),
            "to_ack": gap(self.command, self.result),
            "e2e": gap(start, self.result),
        }


def load(paths: Iterable[pathlib.Path]) -> list[Envelope]:
    files: list[pathlib.Path] = []
    for p in paths:
        files += sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    messages = [m for f in files for m in read_session(f)]
    # 시계 해상도가 거칠면(Windows 15.6 ms) 같은 mono가 생긴다 — 그때는 경로 순서대로
    return sorted(messages, key=lambda m: (m.mono, STAGE_ORDER.get(m.type, len(STAGE_ORDER))))


def find_stops(messages: list[Envelope]) -> list[Stop]:
    """mono 순 메시지 → 자동 차단 목록 (각 단계를 이어 붙인다)."""
    stops: list[Stop] = []
    for i, msg in enumerate(messages):
        if msg.type != "guard/decision" or not msg.payload["reason"].startswith(REASON_PREFIX):
            continue
        target = msg.payload["call"]["target"]
        kind = "과열" if "과열" in msg.payload["reason"] else "방치"
        stop = Stop(kind, target, msg)
        before = messages[:i]
        # 차단의 근거가 된 판정: 그 장치가 켜져 있고 과열·방치 조건을 만족한 마지막 fusion/state
        # (같은 mono로 뒤이어 나온 판정 — 꺼진 뒤의 상태 — 을 근거로 잡지 않게 조건으로 찾는다)
        stop.trigger = next(
            (
                m
                for m in reversed(before)
                if m.type == "fusion/state" and _justifies(m, target, kind)
            ),
            None,
        )
        if kind == "과열":
            stop.reading = _first_hot_reading(before, target)
        else:
            stop.unattended_s = _grace_s(stop.trigger)
        for m in messages[i + 1 :]:
            p = m.payload
            if stop.command is None:
                if (
                    m.type == "control/command"
                    and m.session_id == msg.session_id
                    and p["target"] == target
                    and p["cmd"] == "OFF"
                ):
                    stop.command = m
            elif m.type == "control/result" and p["seq"] == stop.command.payload["seq"]:
                stop.result = m
                break
        stops.append(stop)
    return stops


def _justifies(state: Envelope, target: str, kind: str) -> bool:
    evidence = state.payload["evidence"]
    heater = evidence["heaters"].get(target) or {}
    if not heater.get("on"):
        return False
    if kind == "과열":
        return (heater.get("temperature_c") or 0.0) >= DANGER_C
    return evidence["absent_s"] >= STOP_ABSENT_S


def _first_hot_reading(before: list[Envelope], device: str) -> Envelope | None:
    """이번 과열에서 그 장치가 처음 240°C 이상이 된 온도 (그 앞의 값은 240°C 아래)."""
    first = None
    for m in reversed(before):
        if m.type != "sensor/reading" or m.payload["device_id"] != device:
            continue
        if m.payload["temperature_c"] < DANGER_C:
            break
        first = m
    return first


def _grace_s(trigger: Envelope | None) -> float | None:
    """방치 판정(사람 없음 30초) 뒤 차단까지 기다린 초 = 판정 근거의 사람 없는 시간 − 30초.

    중간에 DANGER가 끼어 UNATTENDED가 끊겨도 사람 없는 시간은 이어지므로 이것으로 센다.
    """
    if trigger is None:
        return None
    return round(trigger.payload["evidence"]["absent_s"] - UNATTENDED_S, 1)


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.1f}"


def report(stops: list[Stop]) -> str:
    names = [n for n, _ in SEGMENTS]
    lines = [" | ".join(["종류", "장치", *names, "결과", "유예(s)"])]
    for s in stops:
        seg = s.segments()
        ok = "-" if s.result is None else ("ok" if s.result.payload["ok"] else "실패")
        row = [s.kind, s.target, *(_fmt(seg[n]) for n in names), ok, _fmt(s.unattended_s)]
        lines.append(" | ".join(row))
    for kind in ("과열", "방치"):
        e2e = [s.segments()["e2e"] for s in stops if s.kind == kind]
        e2e = [v for v in e2e if v is not None]
        if e2e:
            lines.append(
                f"{kind} {len(e2e)}건: 감지 → 차단 확인 평균 {sum(e2e) / len(e2e):.1f} ms, "
                f"최대 {max(e2e):.1f} ms"
            )
    lines += [f"  {n}: {d}" for n, d in SEGMENTS]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="녹화에서 자동 차단의 감지 → 차단 지연을 계산한다")
    parser.add_argument("paths", nargs="+", type=pathlib.Path, help="녹화 파일 또는 폴더")
    args = parser.parse_args(argv)
    stops = find_stops(load(args.paths))
    if not stops:
        print("자동 차단이 없습니다 (guard/decision의 reason이 '자동 차단'으로 시작하는 것)")
        return 1
    print(report(stops))
    return 0


if __name__ == "__main__":
    sys.exit(main())
