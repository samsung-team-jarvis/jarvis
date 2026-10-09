"""온도 시나리오 25개 생성 (FUS-05).

사건 목록 → 1초씩 가상 주방 흉내 → 정답 State가 붙은 시나리오 YAML (scenarios/temp/).

python -m services.simulator.temp_scenarios           # 다시 만들기
python -m services.simulator.temp_scenarios --check   # 파일이 이 코드와 같은지만 확인 (테스트용)

온도는 가상 주방과 같은 규칙(`common.kitchen_link.next_temperature`)으로 계산한다.
정답 State는 아래 기준을 **실제 장치 상태**에 적용해 붙인다
([decision](docs/decisions/2026-10-09-state-criteria.md)).
상황 인식(FUS-07·08)은 메시지(온도·화면·말)만 보고 이 정답을 맞혀야 한다.

| State | 기준 (위가 먼저) |
|---|---|
| SAFE_STOP | 긴급 정지·가상 주방 안전장치(265°C)로 꺼진 뒤, 다시 켜기 전까지 |
| DANGER | 가열 장치가 켜져 있고 온도 ≥ 240°C |
| UNATTENDED | 가열 장치가 켜져 있고 사람이 30초 이상 안 보임, |
|            | 또는 화구 위에 조리 도구가 60초 이상 없음 |
| PREHEAT | 가열 장치가 켜져 있고 온도 < 100°C |
| COOKING | 가열 장치가 켜져 있고 온도 ≥ 100°C |
| IDLE | 가열 장치가 꺼져 있음 |
"""

from __future__ import annotations

import argparse
import dataclasses
import pathlib
import sys

from common.kitchen_link import HARD_LIMIT_C, next_temperature

OUT_DIR = pathlib.Path(__file__).parent / "scenarios" / "temp"

AMBIENT_C = 25.0
PREHEAT_BELOW_C = 100.0  # 이보다 낮으면 예열 중
WARN_C = 200.0  # 주의 (risk=warn) — State는 그대로
DANGER_C = 240.0  # 위험
ABSENT_S = 30  # 사람이 이만큼 안 보이면 방치
EMPTY_S = 60  # 켜진 화구 위에 조리 도구가 이만큼 없으면 방치 (튀김기는 기름이 늘 있어 해당 없음)
TEMP_STEP_S = 5  # 시나리오 파일의 온도 점 간격 (사이는 시뮬레이터가 직선 보간)


@dataclasses.dataclass(frozen=True)
class Spec:
    name: str
    category: str
    description: str
    duration_s: int
    events: list[tuple]  # (초, 종류, 값) — 아래 _apply 참고
    device: str = "burner_1"


def _say(t: int, text: str) -> tuple:
    return (t, "say", text)


B1 = "burner_1"
FRYER = "fryer"

SPECS = [
    # ── 정상: 위험·방치 없이 끝나야 한다 (오탐 확인용) ──
    Spec(
        "t01_normal_medium", "normal", "화구 중불로 2분 조리 후 끔", 150,
        [_say(0, "자비스 1번 화구 켜 줘"), (0, "on", 1),
         _say(5, "자비스 1번 화구 중간으로"), (5, "level", 2),
         _say(125, "자비스 1번 화구 꺼 줘"), (125, "off", None)],
    ),
    Spec("t02_normal_simmer", "normal", "약불로 오래 끓임", 180, [(0, "on", 1)]),
    Spec(
        "t03_normal_sear_then_lower", "normal", "센불로 시작해 20초 뒤 중불로 낮춤", 150,
        [(0, "on", 3), _say(20, "자비스 1번 화구 중간으로 해 줘"), (20, "level", 2),
         (140, "off", None)],
    ),
    Spec(
        "t04_normal_fryer", "normal", "튀김기 중간 세기로 3분", 190,
        [_say(0, "자비스 튀김기 켜 줘"), (0, "on", 1), (3, "level", 2), (180, "off", None)],
        FRYER,
    ),
    Spec(
        "t05_normal_short_step_away", "normal", "조리 중 15초 자리 비웠다 돌아옴 (방치 아님)", 150,
        [(0, "on", 2), (60, "leave", None), (75, "return", None), (140, "off", None)],
    ),
    Spec(
        "t06_normal_pan_lifted", "normal", "조리 중 팬을 20초 들었다 내려놓음 (방치 아님)", 150,
        [(0, "on", 2), (60, "pan_off", None), (80, "pan_on", None), (140, "off", None)],
    ),
    Spec(
        "t07_normal_cool_down", "normal", "조리 후 끄고 팬이 식는 동안 대기", 180,
        [(0, "on", 2), (90, "off", None), _say(100, "오늘 손님 많네")],
    ),
    Spec(
        "t08_normal_warn_then_lower", "normal", "센불로 200°C(주의)까지 갔다가 30초에 약불로", 150,
        [(0, "on", 3), _say(30, "자비스 1번 화구 약하게"), (30, "level", 1), (140, "off", None)],
    ),
    # ── 과열: 240°C 이상을 놓치면 안 된다 ──
    Spec(
        "t09_overheat_left_high", "overheat", "센불로 둔 채 과열, 265°C에서 가상 주방이 끔", 110,
        [_say(0, "자비스 1번 화구 세게"), (0, "on", 3)],
    ),
    Spec("t10_overheat_fryer", "overheat", "튀김기 센불 방치로 과열", 110, [(0, "on", 3)], FRYER),
    Spec(
        "t11_overheat_raised_later", "overheat", "중불로 조리하다 60초에 센불로 올려 과열", 160,
        [(0, "on", 2), _say(60, "자비스 1번 화구 세게 해 줘"), (60, "level", 3),
         _say(110, "자비스 멈춰"), (110, "estop", None)],
    ),
    Spec(
        "t12_overheat_estop", "overheat", "과열 중 '불 더 세게'(거부 대상) 뒤 긴급 정지", 120,
        [(0, "on", 3), _say(45, "자비스 불 더 세게 해 줘"),
         _say(55, "자비스 멈춰"), (55, "estop", None)],
    ),
    Spec(
        "t13_overheat_turned_off", "overheat", "과열 중 사람이 직접 끔", 120,
        [(0, "on", 3), _say(50, "자비스 1번 화구 꺼 줘"), (50, "off", None)],
    ),
    Spec(
        "t14_overheat_while_away", "overheat", "센불로 켜고 자리 비운 사이 과열 (위험 우선)", 110,
        [(0, "on", 3), (15, "leave", None)],
    ),
    # ── 방치: 가열 중 사람이 30초 이상 안 보임 ──
    Spec(
        "t15_unattended_leave", "unattended", "중불 조리 중 자리를 떠나 돌아오지 않음", 150,
        [(0, "on", 2), (40, "leave", None)],
    ),
    Spec(
        "t16_unattended_return", "unattended", "45초 자리 비웠다 돌아옴", 160,
        [(0, "on", 2), (40, "leave", None), (85, "return", None), (150, "off", None)],
    ),
    Spec(
        "t17_unattended_fryer", "unattended", "튀김기 켜 둔 채 자리를 떠남", 150,
        [(0, "on", 2), (50, "leave", None)],
        FRYER,
    ),
    Spec(
        "t18_unattended_low_heat", "unattended", "약불이라도 자리를 오래 비우면 방치", 150,
        [(0, "on", 1), (30, "leave", None)],
    ),
    Spec(
        "t19_unattended_near_miss", "unattended", "25초씩 두 번 자리 비움 (방치 아님)", 150,
        [(0, "on", 2), (30, "leave", None), (55, "return", None), (60, "leave", None),
         (85, "return", None), (140, "off", None)],
    ),
    Spec(
        "t20_unattended_off_then_leave", "unattended", "불을 끄고 자리를 떠남 (방치 아님)", 120,
        [(0, "on", 2), _say(60, "자비스 1번 화구 꺼 줘"), (60, "off", None), (65, "leave", None)],
    ),
    # ── 가열 장치 켜짐 방치: 사람은 있어도 빈 화구·끄지 않은 장치 ──
    Spec(
        "t21_left_on_pan_removed", "left_on", "조리를 마치고 팬만 내리고 화구는 켜 둠", 150,
        [(0, "on", 2), (60, "pan_off", None)],
    ),
    Spec(
        "t22_left_on_empty_burner", "left_on", "팬 없이 화구를 켜 놓음", 100,
        [(0, "pan_off", None), _say(0, "자비스 1번 화구 켜 줘"), (0, "on", 1)],
    ),
    Spec(
        "t23_left_on_pan_back", "left_on", "팬을 40초 내렸다 다시 올림 (방치 아님)", 150,
        [(0, "on", 2), (50, "pan_off", None), (90, "pan_on", None), (140, "off", None)],
    ),
    Spec(
        "t24_left_on_pan_removed_and_leave", "left_on", "팬을 내리고 자리까지 떠남", 120,
        [(0, "on", 2), (50, "pan_off", None), (60, "leave", None)],
    ),
    Spec(
        "t25_left_on_fryer_after_frying", "left_on", "튀김을 마치고 튀김기를 켜 둔 채 떠남", 150,
        [(0, "on", 2), _say(70, "다 튀겼다"), (75, "leave", None)],
        FRYER,
    ),
]  # fmt: skip


@dataclasses.dataclass
class World:
    """가상 주방의 실제 상태 (시나리오 작성용 정답)."""

    level: int = 0
    person: bool = True
    cookware: bool = True
    safe_stop: bool = False
    temp: float = AMBIENT_C
    absent_since: int | None = None
    empty_since: int | None = None


def _apply(w: World, t: int, kind: str, value) -> None:
    if kind == "on":
        w.level, w.safe_stop = value, False
    elif kind == "level":
        w.level = value
    elif kind == "off":
        w.level = 0
    elif kind == "estop":
        w.level, w.safe_stop = 0, True
    elif kind == "leave":
        w.person, w.absent_since = False, t
    elif kind == "return":
        w.person, w.absent_since = True, None
    elif kind == "pan_off":
        w.cookware, w.empty_since = False, t
    elif kind == "pan_on":
        w.cookware, w.empty_since = True, None
    elif kind != "say":
        raise ValueError(f"모르는 사건: {kind}")


def label(w: World, t: int, device: str) -> str:
    """정답 State (기준표는 모듈 설명)."""
    if w.safe_stop:
        return "SAFE_STOP"
    if w.level == 0:
        return "IDLE"
    if w.temp >= DANGER_C:
        return "DANGER"
    absent = w.absent_since is not None and t - w.absent_since >= ABSENT_S
    empty = device != FRYER and w.empty_since is not None and t - w.empty_since >= EMPTY_S
    if absent or empty:
        return "UNATTENDED"
    return "PREHEAT" if w.temp < PREHEAT_BELOW_C else "COOKING"


def _objects(w: World, device: str) -> list[str]:
    objs = []
    if w.cookware:
        objs.append("fryer_basket" if device == FRYER else "pan")
    if device != FRYER:
        objs.append("burner_on" if w.level > 0 else "burner_off")
    if w.person:
        objs.append("person")
    return objs


def simulate(spec: Spec) -> dict:
    """1초씩 진행해 온도·화면·정답 State의 시간표를 만든다."""
    w = World()
    by_time: dict[int, list[tuple]] = {}
    for t, kind, value in spec.events:
        by_time.setdefault(t, []).append((kind, value))

    temps, objects, expect, stt = [], [], [], []
    event_times = {t for t, _, _ in spec.events}
    for t in range(spec.duration_s + 1):
        for kind, value in by_time.get(t, []):
            _apply(w, t, kind, value)
            if kind == "say":
                stt.append([t, value])
        if w.level > 0 and w.temp >= HARD_LIMIT_C:  # 가상 주방 자체 안전장치 (interfaces §4.4)
            w.level, w.safe_stop = 0, True
        if t % TEMP_STEP_S == 0 or t in event_times or t == spec.duration_s:
            temps.append([t, round(w.temp, 1)])
        objs = _objects(w, spec.device)
        if not objects or objects[-1][1] != objs:
            objects.append([t, objs])
        state = label(w, t, spec.device)
        if not expect or expect[-1][1] != state:
            expect.append([t, state])
        w.temp = next_temperature(w.temp, w.level)
    return {"temperature_c": temps, "objects": objects, "expect": expect, "stt": stt}


def _flow(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_flow(v) for v in value) + "]"
    if isinstance(value, str):
        return f'"{value}"' if " " in value or not value.isascii() else value
    return str(value)


def render(spec: Spec) -> str:
    sim = simulate(spec)
    lines = [
        "# 생성 파일 — 고치려면 services/simulator/temp_scenarios.py를 고치고 다시 생성한다.",
        "# 값은 가상 주방 온도 규칙으로 계산한 설계값이다 (실측 아님). 정답 기준: FUS-05 decision.",
        f"name: {spec.name}",
        f"category: {spec.category}",
        f"description: {spec.description}",
        f"duration_s: {spec.duration_s}",
        "heartbeat_hz: 1",
        "",
        "sensor:",
        f"  device_id: {spec.device}",
        "  hz: 1",
        "  temperature_c:",
        *(f"    - {_flow(p)}" for p in sim["temperature_c"]),
        "",
        "vision:",
        "  fps: 2",
        "  objects:",
        *(f"    - {_flow(o)}" for o in sim["objects"]),
        "",
        "stt:" + ("" if sim["stt"] else " []"),
        *(f"  - {_flow(s)}" for s in sim["stt"]),
        "",
        "expect:                       # 정답 State: [시각, State] — 그 시각부터 다음 항목 전까지",
        *(f"  - {_flow(e)}" for e in sim["expect"]),
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="FUS-05 온도 시나리오 생성")
    parser.add_argument("--check", action="store_true", help="파일이 최신인지만 확인")
    args = parser.parse_args()

    expected = {OUT_DIR / f"{spec.name}.yaml": render(spec) for spec in SPECS}
    if args.check:
        stale = [
            p.name for p, text in expected.items()
            if not p.exists() or p.read_bytes().decode("utf-8") != text
        ]  # fmt: skip
        extra = sorted({p.name for p in OUT_DIR.glob("*.yaml")} - {p.name for p in expected})
        if stale or extra:
            print(f"다시 생성 필요: {stale} / 코드에 없는 파일: {extra}")
            return 1
        print(f"OK: {len(expected)}개 최신")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in expected.items():
        path.write_bytes(text.encode("utf-8"))  # Windows에서도 LF
    print(f"{len(expected)}개 생성: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
