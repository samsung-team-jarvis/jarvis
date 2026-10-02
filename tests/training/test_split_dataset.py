import json

from common.function_call import PARAMS
from training.llm import build_seed as bs
from training.llm import split_dataset as sd

SPLIT_DIR = bs.OUT_DIR / "split_v1"


def committed() -> dict[str, list[dict]]:
    return {s: sd.load(SPLIT_DIR / f"{s}.jsonl") for s in sd.SPLITS}


def test_no_group_or_sentence_leak() -> None:
    assert sd.leaks(committed()) == []


def test_every_action_in_every_split_and_ratio() -> None:
    splits = committed()
    total = sum(len(rows) for rows in splits.values())
    for s, rows in splits.items():
        assert {r["output"]["action"] for r in rows} == set(PARAMS), s
        assert abs(len(rows) / total - sd.RATIOS[s]) < 0.05, s
        assert all(r["meta"]["split"] == s for r in rows)


def test_calibration_only_from_train() -> None:
    train = {(r["instruction"], json.dumps(r["context"])) for r in committed()["train"]}
    calib = sd.load(SPLIT_DIR / "calib.jsonl")
    assert 300 <= len(calib) <= 1000
    assert all((r["instruction"], json.dumps(r["context"])) in train for r in calib)
    assert all(r["meta"]["source"] != "hard_negative" for r in calib)


def test_split_is_reproducible_from_dataset() -> None:
    """데이터를 다시 나눠도 같은 결과 (Test 고정)."""
    records = sd.load(bs.OUT_DIR / "dataset_v1.jsonl") + sd.load(
        bs.OUT_DIR / "hard_negative_v1.jsonl"
    )
    assignment = sd.assign_groups(records)
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


def test_leak_detection() -> None:
    a, b = rec("g1"), rec("g1", n=1)
    a["meta"]["split"], b["meta"]["split"] = "train", "test"
    assert any("가족 g1" in p for p in sd.leaks({"train": [a], "val": [], "test": [b]}))
