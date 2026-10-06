import json
from collections import Counter

import yaml

from common.function_call import parse_tokens, to_tokens
from training.llm import build_augment as ba
from training.llm import build_seed as bs
from training.llm.split_dataset import load

AUGMENT = bs.OUT_DIR / f"augment_{ba.VERSION}.jsonl"


def committed() -> list[dict]:
    return load(AUGMENT)


def test_every_row_is_valid_train_only_augment() -> None:
    rows = committed()
    assert 100 <= len(rows) <= 400
    for r in rows:
        assert parse_tokens(to_tokens(r["output"])) == r["output"]
        m = r["meta"]
        assert m["split"] == "train" and m["source"] == "augment" and m["error"]
        assert m["group"] == m["template_id"] and m["template_id"].startswith("aug_")


def test_no_sentence_same_as_or_close_to_val_test() -> None:
    """보강 문장이 val·test 문장과 같거나 너무 비슷하면 같은 test로 비교하는 의미가 없다."""
    held_out = [
        r["instruction"] for s in ("val", "test") for r in load(ba.BASE_SPLIT / f"{s}.jsonl")
    ]
    exact = {bs.compact(t) for t in held_out}
    grams = [ba.bigrams(t) for t in held_out]
    for r in committed():
        assert bs.compact(r["instruction"]) not in exact, r["instruction"]
        g = ba.bigrams(r["instruction"])
        assert max(ba.similarity(g, other) for other in grams) < ba.SIMILAR, r["instruction"]


def test_no_overlap_with_train_or_stt_script() -> None:
    train = {bs.compact(r["instruction"]) for r in load(ba.BASE_SPLIT / "train.jsonl")}
    script = bs.stt_script_sentences(bs.STT_SCRIPT)
    texts = [bs.compact(r["instruction"]) for r in committed()]
    assert len(texts) == len(set(texts))
    assert not (set(texts) & (train | script))


def test_templates_are_capped() -> None:
    sheet = yaml.safe_load(ba.SHEET.read_text(encoding="utf-8"))
    counts = Counter(r["meta"]["template_id"] for r in committed())
    assert max(counts.values()) <= sheet["max_per_template"]


def test_committed_augment_matches_sheet() -> None:
    """시트를 고치고 다시 생성하지 않으면 실패한다."""
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    sheet = yaml.safe_load(ba.SHEET.read_text(encoding="utf-8"))
    records, _ = ba.build_augment(plan, sheet, ba.make_blocklist())
    assert [json.dumps(r, ensure_ascii=False) for r in records] == [
        json.dumps(r, ensure_ascii=False) for r in committed()
    ]


def test_blocklist_same_and_similar() -> None:
    block = ba.Blocklist(["1번 화구 켜 주세요"], {bs.compact("타이머 취소")})
    assert block.reason("1번 화구 켜 주세요.") == "same"
    assert block.reason("타이머 취소") == "same"
    assert block.reason("1번 화구를 켜 주세요") == "similar"  # 조각 9개 중 6개가 같다
    assert block.reason("알람 해제해 줘") is None
