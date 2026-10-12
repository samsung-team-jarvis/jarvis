"""오류 유형 보강 (LLM-11): augment_sheet.yaml → data/llm/augment_v1.jsonl (train에만 더한다).

python -m training.llm.build_augment
.venv-llm/bin/python -m training.llm.train_lora --extra data/llm/augment_v1.jsonl --name <이름>

- 문장은 plan_sheet의 슬롯(장치 부르는 말·세기·시간)과 STT 오인식 사전을 그대로 쓴다.
- **누수 방지**: val·test·STT 대본과 띄어쓰기를 지운 문장이 같거나, 글자 두 개씩 묶은 조각이
  `SIMILAR` 이상 겹치는 문장은 뺀다. 보강 방향을 val 오류로 정했으므로 val에도 같은 검사를 한다.
- train과 같은 문장도 뺀다 (이미 있는 문장을 다시 넣지 않는다).
"""

from __future__ import annotations

import argparse
import copy
import pathlib
import random
import sys
from collections import Counter

import yaml

from services.llm_svc.stt_fixes import normalize
from training.llm import build_dataset as bd
from training.llm import build_seed as bs
from training.llm.split_dataset import load

SHEET = pathlib.Path(__file__).with_name("augment_sheet.yaml")
VERSION = "v1"
BASE_SPLIT = bs.OUT_DIR / f"split_{bs.VERSION}"  # 보강할 데이터 (val·test는 그대로 둔다)
# 글자 두 개 조각(bigram)의 Jaccard 유사도가 이 이상이면 val·test와 너무 비슷하다고 본다
SIMILAR = 0.6


def bigrams(text: str) -> set[str]:
    t = bs.compact(text)
    return {t[i : i + 2] for i in range(len(t) - 1)} or {t}


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


class Blocklist:
    """빼야 할 문장들 (같은 문장 + 너무 비슷한 문장)."""

    def __init__(self, held_out: list[str], also_exact: set[str]) -> None:
        self.exact = {bs.compact(t) for t in held_out} | also_exact
        self.grams = [bigrams(t) for t in held_out]

    def reason(self, text: str) -> str | None:
        if bs.compact(text) in self.exact:
            return "same"
        g = bigrams(text)
        if any(similarity(g, other) >= SIMILAR for other in self.grams):
            return "similar"
        return None


def build_augment(plan: dict, sheet: dict, block: Blocklist) -> tuple[list[dict], Counter]:
    """보강 문장과, 뺀 문장 수(이유별). 템플릿마다 장치·값을 돌아가며 최대 `max_per_template`개."""
    rng = random.Random(sheet.get("seed", 0))
    cap = sheet.get("max_per_template", 12)
    records, dropped, seen = [], Counter(), set()
    for action, templates in sheet["templates"].items():
        for t in templates:
            items = []
            for text in bd.alternatives(t["text"]):
                for sentence, output, slots in bs.expand({**t, "text": text}, plan, action):
                    sentence = normalize(sentence)
                    if bs.compact(sentence) in seen:
                        continue
                    seen.add(bs.compact(sentence))
                    why = block.reason(sentence)
                    if why:
                        dropped[why] += 1
                        continue
                    items.append((sentence, output, slots))
            for sentence, output, _ in bs.balanced(items, rng)[:cap]:
                meta = {
                    "template_id": t["id"],
                    "group": t["id"],
                    "tone": t["tone"],
                    "source": "augment",
                    "error": t["error"],
                    "indirect": False,
                    "split": "train",
                }
                context = copy.deepcopy(rng.choice(plan["contexts"]["normal"]))
                records.append(bs.record(sentence, output, context, meta))
    return records, dropped


def make_blocklist(split_dir: pathlib.Path = BASE_SPLIT) -> Blocklist:
    """val·test·STT 대본 문장(닮아도 안 됨) + train 문장(같으면 안 됨)."""
    held_out = [
        r["instruction"] for name in ("val", "test") for r in load(split_dir / f"{name}.jsonl")
    ]
    script = list(bs.stt_script_sentences(bs.STT_SCRIPT))
    train = {bs.compact(r["instruction"]) for r in load(split_dir / "train.jsonl")}
    return Blocklist(held_out + script, train)


def main() -> int:
    parser = argparse.ArgumentParser(description="오류 유형 보강 문장을 만든다 (train 전용)")
    parser.add_argument("--sheet", type=pathlib.Path, default=SHEET)
    parser.add_argument("--out", type=pathlib.Path, default=bs.OUT_DIR / f"augment_{VERSION}.jsonl")
    args = parser.parse_args()

    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    sheet = yaml.safe_load(args.sheet.read_text(encoding="utf-8"))
    try:
        records, dropped = build_augment(plan, sheet, make_blocklist())
    except bs.SheetError as e:
        print(f"시트 오류: {e}", file=sys.stderr)
        return 1
    bs.write_jsonl(args.out, records)
    actions = Counter(r["output"]["action"] for r in records)
    errors = Counter(r["meta"]["error"] for r in records)
    print(f"보강 {len(records)}건 → {args.out}")
    print("  Action: " + ", ".join(f"{a} {n}" for a, n in actions.items()))
    print("  겨냥한 오류: " + ", ".join(f"{e} {n}" for e, n in errors.items()))
    print(
        f"  뺀 문장: val·test·STT 대본·train과 같음 {dropped['same']}, 비슷함 {dropped['similar']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
