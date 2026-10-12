"""LLM-15 실험 데이터: A(more_v1 — 같은 말투 더) · B(variety_v1 — 새 말투). 둘 다 train 전용."""

import json
from collections import Counter

import pytest
import yaml

from common.function_call import parse_tokens, to_tokens
from training.llm import build_augment as ba
from training.llm import build_dataset as bd
from training.llm import build_more as bm
from training.llm import build_seed as bs
from training.llm.split_dataset import load

VARIETY_SHEET = bs.ROOT / "training/llm/variety_sheet.yaml"
MORE = bs.OUT_DIR / f"more_{bm.VERSION}.jsonl"


def held_out() -> list[str]:
    return [r["instruction"] for s in ("val", "test") for r in load(ba.BASE_SPLIT / f"{s}.jsonl")]


def train_groups() -> set[str]:
    return {
        r["meta"].get("group") or r["meta"]["template_id"]
        for r in load(ba.BASE_SPLIT / "train.jsonl")
    }


@pytest.mark.parametrize("path", [bm.VARIETY, MORE])
def test_rows_are_valid_and_train_only(path) -> None:
    for r in load(path):
        assert parse_tokens(to_tokens(r["output"])) == r["output"]
        assert r["meta"]["split"] == "train"


def test_same_size_for_a_fair_comparison() -> None:
    """A와 B는 더하는 문장 수만 같고 뽑는 방식이 다르다."""
    assert len(load(MORE)) == len(load(bm.VARIETY))


@pytest.mark.parametrize("path", [bm.VARIETY, MORE])
def test_no_sentence_same_as_or_close_to_val_test(path) -> None:
    held = held_out()
    exact = {bs.compact(t) for t in held}
    grams = [ba.bigrams(t) for t in held]
    for r in load(path):
        assert bs.compact(r["instruction"]) not in exact, r["instruction"]
        g = ba.bigrams(r["instruction"])
        assert max(ba.similarity(g, other) for other in grams) < ba.SIMILAR, r["instruction"]


@pytest.mark.parametrize("path", [bm.VARIETY, MORE])
def test_no_overlap_with_train_augment_or_stt_script(path) -> None:
    train = {
        bs.compact(r["instruction"])
        for f in (ba.BASE_SPLIT / "train.jsonl", bm.AUGMENT)
        for r in load(f)
    }
    script = bs.stt_script_sentences(bs.STT_SCRIPT)
    texts = [bs.compact(r["instruction"]) for r in load(path)]
    assert len(texts) == len(set(texts))
    assert not (set(texts) & (train | script))


def test_more_uses_only_train_families() -> None:
    groups = train_groups()
    rows = load(MORE)
    assert all(r["meta"]["source"] == "more" and r["meta"]["group"] in groups for r in rows)


def test_variety_templates_are_new_and_capped() -> None:
    sheet = yaml.safe_load(VARIETY_SHEET.read_text(encoding="utf-8"))
    rows = load(bm.VARIETY)
    assert all(r["meta"]["source"] == "variety" for r in rows)
    assert all(r["meta"]["template_id"].startswith("var_") for r in rows)
    counts = Counter(r["meta"]["template_id"] for r in rows)
    assert max(counts.values()) <= sheet["max_per_template"]
    assert {r["output"]["action"] for r in rows} == set(sheet["templates"])  # 14개 Action 모두


def test_committed_variety_matches_sheet() -> None:
    """시트를 고치고 다시 생성하지 않으면 실패한다."""
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    sheet = yaml.safe_load(VARIETY_SHEET.read_text(encoding="utf-8"))
    block = ba.make_blocklist(extra_train=(bm.AUGMENT,))
    records, _ = ba.build_augment(plan, sheet, block)
    assert [json.dumps(r, ensure_ascii=False) for r in records] == [
        json.dumps(r, ensure_ascii=False) for r in load(bm.VARIETY)
    ]


def test_committed_more_matches_generator() -> None:
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    para = yaml.safe_load(bd.PARA_SHEET.read_text(encoding="utf-8"))
    block = ba.make_blocklist(extra_train=(bm.AUGMENT,))
    rows = load(MORE)
    records, _ = bm.build_more(plan, para, train_groups(), block, len(rows))
    assert [json.dumps(r, ensure_ascii=False) for r in records] == [
        json.dumps(r, ensure_ascii=False) for r in rows
    ]
