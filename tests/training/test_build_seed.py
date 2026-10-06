import json
import pathlib
import random
from collections import Counter

import pytest
import yaml

from common.function_call import (
    ACTIONS,
    DEVICES,
    TIMER_TARGETS,
    V01_ACTIONS,
    parse_tokens,
    to_tokens,
    validate,
)
from training.llm import build_seed as bs

DATA = bs.OUT_DIR
SEED = DATA / f"seed_{bs.VERSION}.jsonl"
HARD = DATA / f"hard_negative_{bs.VERSION}.jsonl"


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
    assert 700 <= len(rows) <= 1000
    assert {r["output"]["action"] for r in rows} == set(ACTIONS)
    assert {r["output"].get("target") for r in rows} >= set(DEVICES)
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
        if m["category"] == "not_urgent":  # "음악 멈춰"는 긴급 정지가 아니다
            assert r["output"]["action"] == "TURN_OFF"
    # 매장 장치에는 타이머가 없다 → 되묻지 않고 지원 외
    store_timers = [r for r in rows if r["meta"]["template_id"] == "hn_nm_06"]
    assert store_timers and all(r["output"] == {"action": "UNSUPPORTED"} for r in store_timers)


def test_v1_snapshot_is_still_valid() -> None:
    """데이터 v1(스키마 v0.1 때의 고정본)은 다시 만들지 않지만 지금 스키마로도 읽힌다."""
    rows = load(DATA / "dataset_v1.jsonl") + load(DATA / "hard_negative_v1.jsonl")
    assert {r["output"]["action"] for r in rows} == set(V01_ACTIONS)
    for r in rows:
        validate(r["output"])


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
        "hood": ["후드", "환풍기"],
        "burner_1": ["1번 화구", "1번 불", "첫 번째 불"],
        "burner_2": ["2번 화구"],
        "fryer": ["튀김기"],
        "light": ["조명"],
        "aircon": ["에어컨"],
        "fan": ["선풍기"],
        "music": ["음악", "노래"],
        "all": ["전부"],
    },
    "levels": {1: ["약하게"], 3: ["세게"]},
    "device_levels": {"light": {1: ["어둡게"], 3: ["밝게"]}, "music": {1: ["작게"], 3: ["크게"]}},
    "times": {180: ["3분"], 300: ["5분"]},
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
        "devices": ["fryer"],
        "last_target": "{device}",
    }
    [(sentence, output, slots)] = bs.expand(t, SHEET, "TURN_OFF")
    assert sentence == "그거 꺼줘" and output["target"] == "fryer" and slots["device"] == "fryer"


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


def test_default_devices_follow_the_schema() -> None:
    on = {
        "id": "on",
        "text": "{device} 켜줘",
        "output": {"action": "TURN_ON", "target": "{device}"},
    }
    assert {o["target"] for _, o, _ in bs.expand(on, SHEET, "TURN_ON")} == set(DEVICES)
    timer = {
        "id": "tm",
        "text": "{time} 뒤에 {device} 꺼줘",
        "output": {"action": "SET_TIMER", "duration_s": "{time}", "target": "{device}"},
    }
    assert {o["target"] for _, o, _ in bs.expand(timer, SHEET, "SET_TIMER")} == set(TIMER_TARGETS)


def test_level_words_follow_the_device() -> None:
    t = {
        "id": "lv",
        "text": "{device} {level} 해줘",
        "output": {"action": "SET_LEVEL", "target": "{device}", "level": "{level}"},
    }
    got = {s: (o["target"], o["level"]) for s, o, _ in bs.expand(t, SHEET, "SET_LEVEL")}
    assert got["조명 밝게 해줘"] == ("light", 3) and got["음악 작게 해줘"] == ("music", 1)
    assert got["후드 세게 해줘"] == ("hood", 3)
    assert "조명 세게 해줘" not in got and "후드 밝게 해줘" not in got
    volume = {
        "id": "vol",
        "text": "볼륨 {level} 해줘",
        "output": {"action": "SET_LEVEL", "target": "music", "level": "{level}"},
    }  # 문장에 장치가 없으면 정답의 target을 따른다
    assert {s for s, _, _ in bs.expand(volume, SHEET, "SET_LEVEL")} == {
        "볼륨 작게 해줘",
        "볼륨 크게 해줘",
    }


def test_balanced_rotates_devices_and_values() -> None:
    t = {
        "id": "off",
        "text": "{time} 뒤에 {device} 꺼줘",
        "output": {"action": "SET_TIMER", "duration_s": "{time}", "target": "{device}"},
    }
    items = bs.balanced(bs.expand(t, SHEET, "SET_TIMER"), random.Random(0))
    first = items[: len(TIMER_TARGETS)]  # 부르는 말이 3개인 1번 화구도 한 바퀴에 한 번만
    assert {o["target"] for _, o, _ in first} == set(TIMER_TARGETS)
    burner_1 = [o["duration_s"] for _, o, _ in items if o["target"] == "burner_1"]
    assert set(burner_1[:2]) == {180, 300}  # 같은 장치 안에서는 시간을 돌아가며


def test_pick_rotates_cells_and_takes_scarce_templates_first() -> None:
    slot = {
        "id": "slot",
        "text": "{device} 켜줘",
        "output": {"action": "TURN_ON", "target": "{device}"},
    }
    only_music = {
        "id": "music_only",
        "text": "매장이 너무 조용해",
        "output": {"action": "TURN_ON", "target": "music"},
    }
    rng = random.Random(0)
    pools = [(t, bs.balanced(bs.expand(t, SHEET, "TURN_ON"), rng)) for t in (slot, only_music)]
    chosen = bs.pick(pools, 8)
    assert Counter(o["target"] for _, (_, o, _) in chosen) == dict.fromkeys(DEVICES, 1)
    music = next(t for t, (_, o, _) in chosen if o["target"] == "music")
    assert music["id"] == "music_only"  # 한 장치만 다루는 템플릿이 밀려 빠지지 않는다

    pools = [(slot, bs.balanced(bs.expand(slot, SHEET, "TURN_ON"), rng))]
    seen = {bs.compact("후드 켜줘")}
    texts = [s for _, (s, _, _) in bs.pick(pools, 100, seen)]
    assert "후드 켜줘" not in texts and "환풍기 켜줘" in texts and bs.compact("환풍기 켜줘") in seen
