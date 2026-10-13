"""LLM-16 새 말투 v2 (variety_v2.jsonl): train 전용, 누수·중복 없음, 긴급 빠른 경로와 맞는 정답."""

import json
from collections import Counter

import yaml

from common.function_call import parse_tokens, to_tokens
from services.safety_guard.emergency import is_emergency
from training.llm import build_augment as ba
from training.llm import build_more as bm
from training.llm import build_seed as bs
from training.llm.split_dataset import load

SHEET = bs.ROOT / "training/llm/variety_sheet_v2.yaml"
VARIETY2 = bs.OUT_DIR / "variety_v2.jsonl"
TRAIN_ONLY = (bm.AUGMENT, bm.VARIETY)  # 함께 train에 더하는 파일 — 같은 문장이 있으면 안 된다


def test_rows_are_valid_train_only_and_capped() -> None:
    sheet = yaml.safe_load(SHEET.read_text(encoding="utf-8"))
    rows = load(VARIETY2)
    for r in rows:
        assert parse_tokens(to_tokens(r["output"])) == r["output"]
        assert r["meta"]["split"] == "train" and r["meta"]["source"] == "variety"
        assert r["meta"]["template_id"].startswith("var2_")
    counts = Counter(r["meta"]["template_id"] for r in rows)
    assert max(counts.values()) <= sheet["max_per_template"]


def test_no_sentence_same_as_or_close_to_val_test() -> None:
    held = [r["instruction"] for s in ("val", "test") for r in load(ba.BASE_SPLIT / f"{s}.jsonl")]
    exact = {bs.compact(t) for t in held}
    grams = [ba.bigrams(t) for t in held]
    for r in load(VARIETY2):
        assert bs.compact(r["instruction"]) not in exact, r["instruction"]
        g = ba.bigrams(r["instruction"])
        assert max(ba.similarity(g, other) for other in grams) < ba.SIMILAR, r["instruction"]


def test_no_overlap_with_other_train_files_or_stt_script() -> None:
    train = {
        bs.compact(r["instruction"])
        for f in (ba.BASE_SPLIT / "train.jsonl", *TRAIN_ONLY)
        for r in load(f)
    }
    script = bs.stt_script_sentences(bs.STT_SCRIPT)
    texts = [bs.compact(r["instruction"]) for r in load(VARIETY2)]
    assert len(texts) == len(set(texts))
    assert not (set(texts) & (train | script))


def test_fast_path_emergency_sentences_are_labeled_emergency() -> None:
    """긴급 빠른 경로가 LLM보다 먼저 긴급 정지하는 말을 다른 정답으로 가르치지 않는다."""
    for r in load(VARIETY2):
        if is_emergency(f"{bs.WAKE} {r['instruction']}", wake=True):
            assert r["output"]["action"] == "EMERGENCY_STOP", r["instruction"]


def test_committed_variety_v2_matches_sheet() -> None:
    """시트를 고치고 다시 생성하지 않으면 실패한다."""
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    sheet = yaml.safe_load(SHEET.read_text(encoding="utf-8"))
    records, _ = ba.build_augment(plan, sheet, ba.make_blocklist(extra_train=TRAIN_ONLY))
    assert [json.dumps(r, ensure_ascii=False) for r in records] == [
        json.dumps(r, ensure_ascii=False) for r in load(VARIETY2)
    ]
