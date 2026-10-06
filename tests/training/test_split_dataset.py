import json

from common.function_call import ACTIONS, DEVICES
from training.llm import build_seed as bs
from training.llm import split_dataset as sd

SPLIT_DIR = sd.SPLIT_DIR


def committed() -> dict[str, list[dict]]:
    return {s: sd.load(SPLIT_DIR / f"{s}.jsonl") for s in sd.SPLITS}


def test_no_group_or_sentence_leak() -> None:
    assert sd.leaks(committed()) == []


def test_every_action_in_every_split_and_ratio() -> None:
    splits = committed()
    total = sum(len(rows) for rows in splits.values())
    for s, rows in splits.items():
        assert {r["output"]["action"] for r in rows} == set(ACTIONS), s
        assert {r["output"].get("target") for r in rows} >= set(DEVICES), s
        assert abs(len(rows) / total - sd.RATIOS[s]) < 0.05, s
        assert all(r["meta"]["split"] == s for r in rows)


def test_test_split_has_hard_negatives_guard_must_reject() -> None:
    """Unsafe Rate를 test로 잴 수 있어야 한다."""
    test = committed()["test"]
    assert any(r["meta"].get("expect_guard") == "REJECT" for r in test)


def test_every_ask_kind_and_indirect_speech_in_every_split() -> None:
    """v1은 장치·시간 되묻기와 간접 발화가 거의 val·test에만 있어 train에서 배울 수 없었다."""
    splits = committed()
    kinds = {
        (r["output"]["for_action"], tuple(r["output"]["missing"]))
        for rows in splits.values()
        for r in rows
        if r["output"]["action"] == "ASK_CLARIFY"
    }
    for s, rows in splits.items():
        asks = [r["output"] for r in rows if r["output"]["action"] == "ASK_CLARIFY"]
        assert {(o["for_action"], tuple(o["missing"])) for o in asks} == kinds, s
        indirect = {r["output"]["action"] for r in rows if r["meta"].get("indirect")}
        assert {"TURN_ON", "TURN_OFF", "SET_LEVEL", "SET_TIMER"} <= indirect, s


def test_families_of_the_previous_version_keep_their_split() -> None:
    """v1의 train·val에 있던 가족이 v2의 test로 넘어가지 않는다 (규칙 파서를 v1 val로 고쳤다)."""
    before = sd.load_groups(sd.BASE_GROUPS)
    now = sd.load_groups(SPLIT_DIR / "groups.json")
    assert len(set(before) & set(now)) > 150
    assert not {g: (before[g], now[g]) for g in before if g in now and before[g] != now[g]}


def test_calibration_only_from_train() -> None:
    train = {(r["instruction"], json.dumps(r["context"])) for r in committed()["train"]}
    calib = sd.load(SPLIT_DIR / "calib.jsonl")
    assert 300 <= len(calib) <= 1000
    assert all((r["instruction"], json.dumps(r["context"])) in train for r in calib)
    assert all(r["meta"]["source"] != "hard_negative" for r in calib)


def test_split_is_reproducible_from_dataset() -> None:
    """데이터를 다시 나눠도 같은 결과 (Test 고정)."""
    records = sd.load(bs.OUT_DIR / f"dataset_{bs.VERSION}.jsonl") + sd.load(
        bs.OUT_DIR / f"hard_negative_{bs.VERSION}.jsonl"
    )
    assignment = sd.assign_groups(records, fixed=sd.load_groups(sd.BASE_GROUPS))
    assert assignment == json.loads((SPLIT_DIR / "groups.json").read_text(encoding="utf-8"))
    assert sd.split_records(records, assignment) == committed()


def rec(group: str, action: str = "TURN_ON", n: int = 0) -> dict:
    return {
        "instruction": f"{group}-{n}",
        "context": {},
        "output": {"action": action},
        "meta": {"template_id": group, "group": group, "source": "seed"},
    }


def test_assign_keeps_family_together_and_covers_splits() -> None:
    records = [rec(f"g{i}", n=k) for i in range(10) for k in range(i + 1)]  # 크기 1~10
    assignment = sd.assign_groups(records)
    splits = sd.split_records(records, assignment)
    assert sd.leaks(splits) == []
    assert all(splits[s] for s in sd.SPLITS)  # 모든 split에 이 묶음이 있음


def test_assign_keeps_fixed_families_and_fills_around_them() -> None:
    records = [rec(f"g{i}", n=k) for i in range(10) for k in range(5)]
    fixed = {"g0": "test", "g1": "test", "g2": "val", "gone": "train"}  # 없어진 가족은 무시
    assignment = sd.assign_groups(records, fixed=fixed)
    assert {g: assignment[g] for g in ("g0", "g1", "g2")} == {
        "g0": "test",
        "g1": "test",
        "g2": "val",
    }
    assert "gone" not in assignment
    new = [assignment[f"g{i}"] for i in range(3, 10)]
    assert new.count("train") == 7  # test·val은 이미 찼으니 새 가족은 모자란 train으로


def test_ask_kinds_are_split_separately() -> None:
    def ask(group: str, for_action: str, n: int) -> dict:
        r = rec(group, "ASK_CLARIFY", n)
        r["output"].update(for_action=for_action, missing=["target"])
        return r

    records = [
        ask(f"{fa}{i}", fa, k) for fa in ("TURN_ON", "TURN_OFF") for i in range(4) for k in range(3)
    ]
    splits = sd.split_records(records, sd.assign_groups(records))
    for rows in splits.values():
        assert {r["output"]["for_action"] for r in rows} == {"TURN_ON", "TURN_OFF"}


def test_leak_detection() -> None:
    a, b = rec("g1"), rec("g1", n=1)
    a["meta"]["split"], b["meta"]["split"] = "train", "test"
    assert any("가족 g1" in p for p in sd.leaks({"train": [a], "val": [], "test": [b]}))
