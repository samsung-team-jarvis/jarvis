import collections

import pytest

from common.kitchen_link import HARD_LIMIT_C
from services.simulator import temp_scenarios as ts
from services.simulator.scenario import load

FILES = sorted(ts.OUT_DIR.glob("*.yaml"))


def test_generated_files_are_up_to_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """scenarios/temp/*.yaml은 temp_scenarios.py로만 만든다 (손으로 고치면 여기서 걸린다)."""
    monkeypatch.setattr("sys.argv", ["temp_scenarios", "--check"])
    assert ts.main() == 0


def test_count_and_categories() -> None:
    """PLAN FUS-05: 20~30개, 정상·과열·방치·가열 장치 켜짐 방치."""
    scenarios = [load(p) for p in FILES]
    assert 20 <= len(scenarios) <= 30
    counts = collections.Counter(sc.category for sc in scenarios)
    assert set(counts) == {"normal", "overheat", "unattended", "left_on"}
    assert min(counts.values()) >= 5


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_every_scenario_has_expected_states(path) -> None:
    sc = load(path)
    assert sc.expect and sc.sensor is not None and sc.sensor.device_id in ("burner_1", "fryer")
    states = {s for _, s in sc.expect}
    risky = states & {"DANGER", "UNATTENDED"}
    if sc.category == "normal":
        assert not risky  # 정상 시나리오는 오탐 확인용
    if sc.category == "overheat":
        assert "DANGER" in states


def test_temperature_follows_virtual_kitchen_rule() -> None:
    """센불(세기 3)로 켜 두면 41초에 240°C를 넘고, 76초에 가상 주방 안전장치(265°C)가 끈다."""
    sc = load(ts.OUT_DIR / "t09_overheat_left_high.yaml")
    assert sc.state_at(40) == "COOKING" and sc.state_at(41) == "DANGER"
    assert sc.state_at(76) == "SAFE_STOP"
    peak = max(v for _, v in sc.sensor.temperature_c)
    assert ts.DANGER_C < peak < HARD_LIMIT_C + 5


@pytest.mark.parametrize(
    ("name", "t", "state"),
    [
        ("t05_normal_short_step_away", 80, "COOKING"),  # 15초 자리 비움은 방치 아님
        ("t15_unattended_leave", 69, "COOKING"),
        ("t15_unattended_leave", 70, "UNATTENDED"),  # 떠난 지 30초
        ("t14_overheat_while_away", 45, "DANGER"),  # 위험이 방치보다 먼저
        ("t19_unattended_near_miss", 80, "COOKING"),  # 연속 30초가 안 됨
        ("t21_left_on_pan_removed", 120, "UNATTENDED"),  # 빈 화구 60초
        ("t23_left_on_pan_back", 100, "COOKING"),
        ("t25_left_on_fryer_after_frying", 104, "COOKING"),  # 튀김기는 빈 화구 규칙 없음
        ("t13_overheat_turned_off", 50, "IDLE"),
    ],
)
def test_criteria_examples(name: str, t: int, state: str) -> None:
    assert load(ts.OUT_DIR / f"{name}.yaml").state_at(t) == state
