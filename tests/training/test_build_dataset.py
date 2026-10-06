import json
import pathlib
from collections import Counter, defaultdict

import pytest
import yaml

from common.function_call import ACTIONS, DEVICES, LEVELS, parse_tokens, to_tokens
from training.llm import build_dataset as bd
from training.llm import build_seed as bs

DATASET = bs.OUT_DIR / f"dataset_{bs.VERSION}.jsonl"


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
    assert 2500 <= len(rows) <= 3500
    assert {r["output"]["action"] for r in rows} == set(ACTIONS)
    for r in rows:
        assert parse_tokens(to_tokens(r["output"])) == r["output"]
        assert r["meta"]["split"] is None and r["meta"]["group"]
    assert {r["meta"]["source"] for r in rows} == {"seed", "paraphrase"}


def test_devices_and_levels_are_even() -> None:
    """부르는 말이 많은 장치·한 장치만 다루는 템플릿 때문에 한쪽으로 쏠리지 않는다."""
    rows = load(DATASET)
    for action in ("TURN_ON", "TURN_OFF", "SET_LEVEL"):
        counts = Counter(r["output"]["target"] for r in rows if r["output"]["action"] == action)
        assert set(counts) >= set(DEVICES), action
        assert max(counts.values()) <= 1.2 * min(counts.values()), (action, counts)
    cells = Counter(
        (r["output"]["target"], r["output"]["level"])
        for r in rows
        if r["output"]["action"] == "SET_LEVEL"
    )
    assert len(cells) == len(DEVICES) * len(LEVELS)
    assert max(cells.values()) <= 1.3 * min(cells.values()), cells


def test_ask_kinds_are_not_one_sided() -> None:
    """v1은 되묻기 230건 중 172건이 "세기 빠짐"이었다."""
    asks = [r["output"] for r in load(DATASET) if r["output"]["action"] == "ASK_CLARIFY"]
    kinds = Counter((o["for_action"], tuple(o["missing"])) for o in asks)
    assert len(kinds) == 7
    for kind, n in kinds.items():
        assert 0.08 <= n / len(asks) <= 0.35, (kind, n)


def test_same_sentence_has_one_answer() -> None:
    answers = defaultdict(set)
    for r in load(DATASET):
        answers[bs.compact(r["instruction"])].add(to_tokens(r["output"]))
    assert not {text: a for text, a in answers.items() if len(a) > 1}


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
        "fryer": ["튀김기"],
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
        "targets": {"CANCEL_TIMER": 5},
        "paraphrases": {"ct_01": [{"tone": "명령", "text": "(타임머|알람) (꺼|취소)"}]},
    }
    records, shortfall = bd.build_dataset(TINY_PLAN, para, set())
    # 바꿔 쓴 4문장 중 "타임머 취소"는 고치면 Seed의 "타이머 취소"와 같아져 하나로 합쳐진다
    assert len(records) == 4 and not shortfall
    texts = {r["instruction"] for r in records}
    assert all("타임머" not in t for t in texts)  # ④ 사전 적용 (타임머 → 타이머)
    fixed = [r for r in records if "raw_instruction" in r["meta"]]
    assert fixed and all(r["meta"]["raw_instruction"].startswith("타임머") for r in fixed)
    assert all(r["meta"]["group"] == "ct_01" for r in records)


def test_unknown_parent_is_an_error() -> None:
    para = {"targets": {}, "paraphrases": {"nope_01": [{"tone": "명령", "text": "x"}]}}
    with pytest.raises(bs.SheetError, match="nope_01"):
        bd.build_dataset(TINY_PLAN, para, set())


def test_paraphrase_can_narrow_devices() -> None:
    plan = {
        **TINY_PLAN,
        "targets": {"CANCEL_TIMER": 5},
        "templates": {
            "CANCEL_TIMER": [
                {
                    "id": "ct_06",
                    "tone": "명령",
                    "text": "{device} 타이머 취소",
                    "output": {"action": "CANCEL_TIMER", "target": "{device}"},
                }
            ]
        },
    }
    para = {
        "targets": {"CANCEL_TIMER": 20},
        "paraphrases": {
            "ct_06": [{"tone": "명령", "text": "{device} 타이머 꺼", "devices": ["hood"]}]
        },
    }
    records, _ = bd.build_dataset(plan, para, set())
    by_source = defaultdict(set)
    for r in records:
        by_source[r["meta"]["source"]].add(r["output"]["target"])
    assert by_source["seed"] == {"hood", "burner_1", "burner_2", "fryer", "all"}
    assert by_source["paraphrase"] == {"hood"}
