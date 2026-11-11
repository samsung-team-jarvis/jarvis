"""시나리오 정답 State(`expected`)를 판정 기준으로 다시 계산해 파일과 비교한다 (#139 리뷰 의견).

정답을 만든 규칙이다: docs/decisions/2026-11-09-state-rules.md. 판정 기준이나 시나리오를 고치면
이 테스트가 정답(`expected`)도 같이 고치라고 알려 준다. `fusion_svc`와 따로 구현했다 — 버스 메시지가
아니라 시나리오의 시간표(세기·보이는 클래스·발화)를 바로 읽는다.
"""

import pathlib

import pytest

from services.audio_svc.wake import is_wake
from services.safety_guard.emergency import is_emergency
from services.simulator.runner import heater_ticks
from services.simulator.scenario import Scenario, expected_at, load

SCENARIOS = sorted(
    (pathlib.Path(__file__).parents[2] / "services/simulator/scenarios").glob("*.yaml")
)


def labels(sc: Scenario) -> list[str]:
    """1초마다 정답 State. 위에서부터 먼저 맞는 것 (decision의 표)."""
    out: list[str] = []
    safe_stop = False
    was_tripped = False
    hot: set[str] = set()
    heating_since: int | None = None
    absent_since: int | None = None
    for t, tick in enumerate(heater_ticks(sc.heaters, sc.duration_s)):
        on = any(level > 0 for level in tick.levels.values())
        heating_since = (t if heating_since is None else heating_since) if on else None
        person = "person" in (sc.vision.visible_at(t) if sc.vision else [])
        absent_since = None if person else (t if absent_since is None else absent_since)

        # 1 SAFE_STOP: 긴급 정지 또는 자체 차단(새로 생길 때) → 모두 꺼지고 모두 100°C 아래면 해제
        if any(at == t and is_emergency(text, is_wake(text)) for at, text in sc.stt):
            safe_stop = True
        if tick.safe_stop and not was_tripped:
            safe_stop = True
        was_tripped = tick.safe_stop
        if safe_stop and not on and all(v < 100 for v in tick.temps.values()):
            safe_stop = False
        # 2 DANGER: 240°C 이상, 230°C 아래에서 해제
        for name, v in tick.temps.items():
            if v >= 240:
                hot.add(name)
            elif v < 230:
                hot.discard(name)
        # 3 UNATTENDED: 켜진 채 사람 없음 30초 (켜진 때부터)
        absent = 0 if not on or absent_since is None else t - max(absent_since, heating_since)

        if safe_stop:
            out.append("SAFE_STOP")
        elif hot:
            out.append("DANGER")
        elif on and absent >= 30:
            out.append("UNATTENDED")
        elif on and any(tick.temps[h] >= 100 for h, lv in tick.levels.items() if lv > 0):
            out.append("COOKING")
        elif on:
            out.append("PREHEAT")
        else:
            out.append("IDLE")
    return out


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_expected_matches_the_state_rules(path: pathlib.Path) -> None:
    sc = load(path)
    assert sc.heaters is not None and sc.expected
    wrong = [
        (t, expected_at(sc, t), want)
        for t, want in enumerate(labels(sc))
        if expected_at(sc, t) != want
    ]
    assert wrong == [], "(시각, 파일의 expected, 규칙으로 계산) — 판정 기준이나 시나리오를 확인"
