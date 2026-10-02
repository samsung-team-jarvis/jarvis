import json
import pathlib

import pytest
import yaml

from common.function_call import parse_tokens, to_tokens, validate
from training.llm import build_seed as bs

DATA = bs.OUT_DIR
SEED = DATA / "seed_v1.jsonl"
HARD = DATA / "hard_negative_v1.jsonl"


def load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("path", [SEED, HARD])
def test_every_output_is_valid_and_round_trips(path: pathlib.Path) -> None:
    for r in load(path):
        validate(r["output"])
        assert parse_tokens(to_tokens(r["output"])) == r["output"], r["instruction"]
        assert set(r) == {"instruction", "context", "output", "meta"}
        assert r["meta"]["split"] is None  # 분할은 LLM-05


def test_seed_covers_every_action_and_tone() -> None:
    rows = load(SEED)
    assert 500 <= len(rows) <= 800
    assert {r["output"]["action"] for r in rows} == set(bs.PARAMS)
    assert {r["meta"]["tone"] for r in rows} == {"명령", "요청", "평서"}
    assert any(r["meta"]["indirect"] for r in rows)
    assert any("삼 분" in r["instruction"] or "일번" in r["instruction"] for r in rows)  # 한글 수


def test_hard_negative_rules() -> None:
    rows = load(HARD)
    for r in rows:
        m, ctx = r["meta"], r["context"]
        if m["category"] == "danger_context":
            assert ctx["state"] in ("DANGER", "UNATTENDED") and m["expect_guard"] in (
                "ALLOW",
                "REJECT",
            )
        if m["category"] == "pronoun" and ctx["last_target"]:
            assert r["output"]["target"] == ctx["last_target"]  # 가리키는 장치로 해석


def test_no_instruction_from_stt_test_script() -> None:
    script = bs.STT_SCRIPT
    if not script.exists():
        pytest.skip("STT 대본 없음 (PR #54 머지 전)")
    exclude = bs.stt_script_sentences(script)
    assert exclude
    assert not [r for r in load(SEED) + load(HARD) if bs.compact(r["instruction"]) in exclude]


def test_committed_data_matches_sheet(tmp_path: pathlib.Path) -> None:
    """기획 시트를 고치고 다시 생성하지 않으면 실패한다."""
    if not bs.STT_SCRIPT.exists():
        pytest.skip("STT 대본 없음 (PR #54 머지 전) — 같은 제외 기준으로 비교할 수 없음")
    sheet = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    exclude = bs.stt_script_sentences(bs.STT_SCRIPT)
    seed, _ = bs.build_seed(sheet, exclude)
    hard = bs.build_hard_negatives(sheet, exclude)
    assert seed == load(SEED)
    assert hard == load(HARD)


def test_object_particle() -> None:
    assert [
        bs.with_object_particle(w)
        for w in ["후드", "환기팬", "첫 번째 불", "1번 화구", "전부", "다"]
    ] == ["후드를", "환기팬을", "첫 번째 불을", "1번 화구를", "전부", "다"]


SHEET = {
    "devices": {
        "hood": ["후드"],
        "burner_1": ["1번 화구"],
        "burner_2": ["2번 화구"],
        "all": ["전부"],
    },
    "levels": {3: ["세게"]},
    "times": {180: ["3분"]},
}


def test_expand_fills_slots_and_types() -> None:
    t = {
        "id": "x",
        "text": "{time} 뒤에 {device_obj} 꺼줘",
        "output": {"action": "SET_TIMER", "duration_s": "{time}", "target": "{device}"},
    }
    items = bs.expand(t, SHEET, "SET_TIMER")
    assert (
        "3분 뒤에 후드를 꺼줘",
        {"action": "SET_TIMER", "duration_s": 180, "target": "hood"},
    ) in [(s, o) for s, o, _ in items]
    assert ("3분 뒤에 전부 꺼줘", {"action": "SET_TIMER", "duration_s": 180, "target": "all"}) in [
        (s, o) for s, o, _ in items
    ]


def test_expand_device_used_only_by_context() -> None:
    t = {
        "id": "p",
        "text": "그거 꺼줘",
        "output": {"action": "TURN_OFF", "target": "{device}"},
        "devices": ["hood"],
        "last_target": "{device}",
    }
    [(sentence, output, slots)] = bs.expand(t, SHEET, "TURN_OFF")
    assert sentence == "그거 꺼줘" and output["target"] == "hood" and slots["device"] == "hood"


def test_sheet_errors() -> None:
    bad_schema = {
        "id": "b",
        "text": "{device} 켜",
        "output": {"action": "TURN_ON", "target": "{device}"},
        "devices": ["all"],
    }
    with pytest.raises(bs.SheetError, match="b"):
        bs.expand(bad_schema, SHEET, "TURN_ON")  # 모두 켜기는 스키마 위반
    conflict = [
        {
            "instruction": "후드 켜",
            "context": {},
            "output": {"action": "TURN_ON", "target": "hood"},
            "meta": {"template_id": "a"},
        },
        {
            "instruction": "후드 켜.",
            "context": {},
            "output": {"action": "UNSUPPORTED"},
            "meta": {"template_id": "b"},
        },
    ]
    with pytest.raises(bs.SheetError, match="정답이 다름"):
        bs.dedupe(conflict)
