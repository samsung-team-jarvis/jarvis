import json

import pytest

from bench import fusion_eval as fe
from services.simulator.scenario import expected_at, load, parse


class Oracle:
    """정답을 그대로 답하는 판정기 — 평가 도구 자체를 검사한다."""

    def __init__(self, sc):
        self.sc = sc

    def update(self, t, topic, payload):
        pass

    def state(self, t):
        return expected_at(self.sc, t)


class Always:
    def __init__(self, state):
        self.value = state

    def update(self, t, topic, payload):
        pass

    def state(self, t):
        return self.value


def scenario(**extra):
    base = {"name": "t", "duration_s": 9, "heaters": {"burner_1": [[0, 0]]}}
    return parse({**base, **extra})


def test_split_is_by_scenario_and_covers_all_once():
    data = json.loads(fe.SPLIT_FILE.read_text(encoding="utf-8"))
    names = {p.stem for p in fe.SCENARIO_DIR.glob("*.yaml")}
    assert not set(data["val"]) & set(data["test"])
    assert set(data["val"]) | set(data["test"]) == names


def test_oracle_scores_perfect_on_every_scenario():
    ticks = []
    for name in fe.split_names("all"):
        sc = load(fe.SCENARIO_DIR / f"{name}.yaml")
        ticks += fe.run(sc, Oracle(sc))
    result = fe.summarize(ticks)
    assert result["macro_f1"] == pytest.approx(1.0)
    assert result["miss_rate"] == 0 and result["delay_max"] == 0
    assert result["false_alarm_rate"] == 0
    assert result["segments"] > 0


def test_segments_split_by_state_and_measure_delay():
    sc = scenario(expected=[[0, "COOKING"], [3, "UNATTENDED"], [6, "DANGER"], [8, "IDLE"]])
    ticks = fe.run(sc, Always("COOKING"))
    # 3~5초는 늦게 감지, 6~7초는 놓침
    ticks = [fe.Tick(k.scenario, k.t, k.truth, "UNATTENDED" if k.t == 5 else k.pred) for k in ticks]
    segments = fe.danger_segments(ticks)
    assert [(s.state, s.start, s.end, s.delay) for s in segments] == [
        ("UNATTENDED", 3, 5, 2),
        ("DANGER", 6, 7, None),
    ]
    result = fe.summarize(ticks)
    assert result["miss_rate"] == 0.5 and result["missed_list"] == ["t:DANGER@6"]


def test_false_alarm_counts_only_safe_truth():
    sc = scenario(expected=[[0, "IDLE"], [5, "DANGER"]])
    result = fe.summarize(fe.run(sc, Always("DANGER")))
    assert result["false_alarm_rate"] == 1.0  # IDLE 5초 모두 위험으로 판정
    assert result["miss_rate"] == 0


def test_f1_skips_states_absent_from_truth_and_prediction():
    sc = scenario(expected=[[0, "IDLE"]])
    macro, per = fe.state_f1(fe.run(sc, Always("IDLE")))
    assert macro == 1.0 and list(per) == ["IDLE"]


def test_temperature_only_sees_overheat_but_not_absence():
    sc = load(fe.SCENARIO_DIR / "unattended_overheat.yaml")
    ticks = fe.run(sc, fe.TemperatureOnly())
    pred = {k.t: k.pred for k in ticks}
    assert pred[50] == "DANGER"  # 240°C 넘음
    assert "UNATTENDED" not in pred.values()


def test_person_only_sees_absence_but_not_heat():
    sc = load(fe.SCENARIO_DIR / "normal_idle.yaml")  # 가열 없이 20~60초 자리 비움
    pred = {k.t: k.pred for k in fe.run(sc, fe.PersonOnly())}
    assert pred[49] == "IDLE" and pred[50] == "UNATTENDED"  # 가열이 없는데 방치로 봄 (오탐)
    sc = load(fe.SCENARIO_DIR / "overheat.yaml")
    assert {k.pred for k in fe.run(sc, fe.PersonOnly())} == {"IDLE"}


def test_cli_prints_metrics(capsys):
    assert fe.main(["--judge", "temp", "--judge", "person", "--split", "val"]) == 0
    out = capsys.readouterr().out
    assert "[temp]" in out and "[person]" in out and "위험 미탐율" in out
