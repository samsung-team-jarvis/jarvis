"""새 말투 v2·v3 (LLM-16·17): train 전용, 누수·중복 없음, 긴급 빠른 경로와 맞는 정답."""

import json
from collections import Counter

import pytest
import yaml

from common.function_call import parse_tokens, to_tokens
from services.safety_guard.emergency import is_emergency
from training.llm import build_augment as ba
from training.llm import build_more as bm
from training.llm import build_seed as bs
from training.llm.split_dataset import load

VARIETY2 = bs.OUT_DIR / "variety_v2.jsonl"
# (시트, 생성 파일, id 앞머리, 함께 train에 더하는 파일 — 같은 문장이 있으면 안 된다)
SHEETS = {
    "v2": ("variety_sheet_v2.yaml", VARIETY2, "var2_", (bm.AUGMENT, bm.VARIETY)),
    "v3": ("variety_sheet_v3.yaml", bs.OUT_DIR / "variety_v3.jsonl", "var3_",
           (bm.AUGMENT, bm.VARIETY, VARIETY2)),
}  # fmt: skip
CASES = pytest.mark.parametrize("version", list(SHEETS))


def sheet_of(version: str) -> dict:
    return yaml.safe_load(
        (bs.ROOT / "training/llm" / SHEETS[version][0]).read_text(encoding="utf-8")
    )


@CASES
def test_rows_are_valid_train_only_and_capped(version: str) -> None:
    _, out, prefix, _ = SHEETS[version]
    sheet = sheet_of(version)
    rows = load(out)
    for r in rows:
        assert parse_tokens(to_tokens(r["output"])) == r["output"]
        assert r["meta"]["split"] == "train" and r["meta"]["source"] == "variety"
        assert r["meta"]["template_id"].startswith(prefix)
    counts = Counter(r["meta"]["template_id"] for r in rows)
    assert max(counts.values()) <= sheet["max_per_template"]


@CASES
def test_no_sentence_same_as_or_close_to_val_test(version: str) -> None:
    held = [r["instruction"] for s in ("val", "test") for r in load(ba.BASE_SPLIT / f"{s}.jsonl")]
    exact = {bs.compact(t) for t in held}
    grams = [ba.bigrams(t) for t in held]
    for r in load(SHEETS[version][1]):
        assert bs.compact(r["instruction"]) not in exact, r["instruction"]
        g = ba.bigrams(r["instruction"])
        assert max(ba.similarity(g, other) for other in grams) < ba.SIMILAR, r["instruction"]


@CASES
def test_no_overlap_with_other_train_files_or_stt_script(version: str) -> None:
    _, out, _, train_only = SHEETS[version]
    train = {
        bs.compact(r["instruction"])
        for f in (ba.BASE_SPLIT / "train.jsonl", *train_only)
        for r in load(f)
    }
    script = bs.stt_script_sentences(bs.STT_SCRIPT)
    texts = [bs.compact(r["instruction"]) for r in load(out)]
    assert len(texts) == len(set(texts))
    assert not (set(texts) & (train | script))


@CASES
def test_fast_path_emergency_sentences_are_labeled_emergency(version: str) -> None:
    """긴급 빠른 경로가 LLM보다 먼저 긴급 정지하는 말을 다른 정답으로 가르치지 않는다."""
    for r in load(SHEETS[version][1]):
        if is_emergency(f"{bs.WAKE} {r['instruction']}", wake=True):
            assert r["output"]["action"] == "EMERGENCY_STOP", r["instruction"]


@CASES
def test_committed_variety_matches_sheet(version: str) -> None:
    """시트를 고치고 다시 생성하지 않으면 실패한다."""
    _, out, _, train_only = SHEETS[version]
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    records, _ = ba.build_augment(
        plan, sheet_of(version), ba.make_blocklist(extra_train=train_only)
    )
    assert [json.dumps(r, ensure_ascii=False) for r in records] == [
        json.dumps(r, ensure_ascii=False) for r in load(out)
    ]
