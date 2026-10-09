"""Hard Negative v2 검수 기준 (LLM-03): 데이터가 지켜야 할 것과 검수 기록이 데이터와 맞는지."""

import csv
import json
import pathlib

import pytest

from common.function_call import to_tokens, validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "llm" / "hard_negative_v2.jsonl"
REVIEW = ROOT / "training" / "llm" / "review" / "hard_negative_v2_review.csv"

ROWS = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines()]


def _of(category: str) -> list[dict]:
    return [r for r in ROWS if r["meta"]["category"] == category]


def test_every_answer_follows_schema() -> None:
    for r in ROWS:
        validate(r["output"])


def test_pronoun_answers_follow_last_target() -> None:
    """대명사("그거 꺼줘")는 직전 장치(last_target)를 가리킨다. 직전 장치가 없으면 되묻는다."""
    for r in _of("pronoun"):
        last, out = r["context"]["last_target"], r["output"]
        if out["action"] == "ASK_CLARIFY":
            assert last is None, r["instruction"]
        else:
            assert out["target"] == last, r["instruction"]


def test_danger_context_rows_have_guard_expectation() -> None:
    """위험 상황 명령은 위험 상태에서 말한 것이고, Guard 기대 판정이 붙어 있어야 한다."""
    rows = _of("danger_context")
    assert rows
    for r in rows:
        assert r["context"]["state"] in ("UNATTENDED", "DANGER", "SAFE_STOP"), r["instruction"]
        assert r["meta"]["expect_guard"] in ("ALLOW", "REJECT"), r["instruction"]


@pytest.mark.parametrize("category", ["negation", "near_miss"])
def test_negation_and_near_miss_do_not_control_devices(category: str) -> None:
    """부정("끄지 마")·비슷한 지원 외("TV 틀어줘")가 장치를 움직이는 명령이 되면 안 된다."""
    for r in _of(category):
        assert r["output"]["action"] == "UNSUPPORTED", r["instruction"]


def test_review_record_matches_data() -> None:
    """검수 기록(CSV)이 지금 데이터와 같은 문장·정답이다. 데이터를 다시 만들면 다시 검수한다."""
    with REVIEW.open(encoding="utf-8-sig", newline="") as f:
        review = list(csv.DictReader(f))
    assert len(review) == len(ROWS)
    for row, r in zip(review, ROWS, strict=True):
        assert row["instruction"] == r["instruction"]
        assert row["정답(함수 토큰)"] == to_tokens(r["output"])
        assert row["검수(OK/수정)"], f"검수 표시 없음: {r['instruction']}"
