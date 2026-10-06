import json
import pathlib

import pytest
import yaml

from common.function_call import V01_ACTIONS, parse_tokens, to_tokens
from training.llm import build_dataset as bd
from training.llm import build_seed as bs

DATASET = bs.OUT_DIR / "dataset_v1.jsonl"


def load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def sheets():
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    para = yaml.safe_load(bd.PARA_SHEET.read_text(encoding="utf-8"))
    return plan, para


def test_alternatives() -> None:
    assert bd.alternatives("(빨리|당장) (멈춰|정지해)") == [
        "빨리 멈춰",
        "빨리 정지해",
        "당장 멈춰",
        "당장 정지해",
    ]
    assert bd.alternatives("{device} 켜줘") == ["{device} 켜줘"]


def test_dataset_shape() -> None:
    rows = load(DATASET)
    assert 2000 <= len(rows) <= 3000
    assert {r["output"]["action"] for r in rows} == set(V01_ACTIONS)  # 데이터 v1은 스키마 v0.1 범위
    for r in rows:
        assert parse_tokens(to_tokens(r["output"])) == r["output"]
        assert r["meta"]["split"] is None and r["meta"]["group"]
    assert {r["meta"]["source"] for r in rows} == {"seed", "paraphrase"}


def test_paraphrase_inherits_parent_answer_and_group() -> None:
    plan, _ = sheets()
    parents = {t["id"]: (a, t) for a, ts in plan["templates"].items() for t in ts}
    for r in load(DATASET):
        m = r["meta"]
        if m["source"] == "paraphrase":
            action, parent = parents[m["group"]]
            assert m["template_id"].startswith(m["group"] + "_p")
            assert r["output"]["action"] == action


def test_no_stt_script_sentence() -> None:
    if not bs.STT_SCRIPT.exists():
        pytest.skip("STT 대본 없음")
    exclude = bs.stt_script_sentences(bs.STT_SCRIPT)
    assert not [r for r in load(DATASET) if bs.compact(r["instruction"]) in exclude]


def test_committed_dataset_matches_sheets() -> None:
    """시트를 고치고 다시 생성하지 않으면 실패한다."""
    if not bs.STT_SCRIPT.exists():
        pytest.skip("STT 대본 없음")
    plan, para = sheets()
    records, _ = bd.build_dataset(plan, para, bs.stt_script_sentences(bs.STT_SCRIPT))
    assert records == load(DATASET)


TINY_PLAN = {
    "seed": 0,
    "devices": {
        "hood": ["후드"],
        "burner_1": ["1번 화구"],
        "burner_2": ["2번 화구"],
        "all": ["다"],
    },
    "levels": {3: ["세게"]},
    "times": {180: ["3분"]},
    "contexts": {
        "normal": [
            {"state": "IDLE", "temperature": 24, "detected_objects": [], "last_target": None}
        ]
    },
    "targets": {"CANCEL_TIMER": 1},
    "templates": {
        "CANCEL_TIMER": [
            {
                "id": "ct_01",
                "tone": "명령",
                "text": "타이머 취소",
                "output": {"action": "CANCEL_TIMER"},
            }
        ]
    },
}


def test_paraphrase_fill_and_stt_normalization() -> None:
    para = {
        "targets": {"CANCEL_TIMER": 3},
        "paraphrases": {"ct_01": [{"tone": "명령", "text": "(타임머|알람) (꺼|취소)"}]},
    }
    records, shortfall = bd.build_dataset(TINY_PLAN, para, set())
    assert len(records) == 3 and not shortfall
    texts = {r["instruction"] for r in records}
    assert all("타임머" not in t for t in texts)  # ④ 사전 적용 (타임머 → 타이머)
    fixed = [r for r in records if "raw_instruction" in r["meta"]]
    assert fixed and all(r["meta"]["raw_instruction"].startswith("타임머") for r in fixed)
    assert all(r["meta"]["group"] == "ct_01" for r in records)


def test_unknown_parent_is_an_error() -> None:
    para = {"targets": {}, "paraphrases": {"nope_01": [{"tone": "명령", "text": "x"}]}}
    with pytest.raises(bs.SheetError, match="nope_01"):
        bd.build_dataset(TINY_PLAN, para, set())
