"""같은 말투 더 뽑기 (LLM-15 실험 A): train 가족 템플릿의 안 쓴 장치·세기·시간 조합을 더한다.

python -m training.llm.build_more    # → data/llm/more_v1.jsonl (variety_v1과 같은 수)
.venv-llm/bin/python -m training.llm.train_lora \\
    --extra data/llm/augment_v1.jsonl --extra data/llm/more_v1.jsonl --name <이름>

- 실험 B(variety_sheet.yaml — 새 말투)와 **같은 수**를 더해, "같은 말투를 더 많이"와
  "새 말투"를 비교한다.
- 템플릿은 데이터 v2의 plan_sheet·paraphrase_sheet 그대로다. 가족(group)이 train인 템플릿만 쓴다.
- 템플릿을 돌아가며 하나씩 뽑는다 (한 템플릿 안에서는 장치·세기·시간을 돌아가며 — `bs.balanced`).
  문장이 고정된 템플릿(긴급 정지·결제 등)은 더 뽑을 문장이 없어, 슬롯이 많은 Action이 많아진다.
- 누수 방지는 보강과 같다 (`build_augment.Blocklist`): val·test·STT 대본과 같거나 비슷한 문장,
  데이터 v2·보강 문장과 같은 문장은 뺀다.
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
from training.llm import build_augment as ba
from training.llm import build_dataset as bd
from training.llm import build_seed as bs
from training.llm.split_dataset import load

VERSION = "v1"
AUGMENT = bs.OUT_DIR / f"augment_{ba.VERSION}.jsonl"
VARIETY = bs.OUT_DIR / "variety_v1.jsonl"  # 같은 수를 맞출 실험 B


def train_templates(plan: dict, para: dict, train_groups: set[str]) -> list[tuple[str, dict]]:
    """(Action, 템플릿) — 가족이 train인 Seed 템플릿과 바꿔 쓴 템플릿. 시트 순서."""
    out = []
    for action, templates in plan["templates"].items():
        out += [(action, t) for t in templates if t["id"] in train_groups]
    for action, templates in bd.paraphrase_templates(plan, para).items():
        out += [(action, t) for t in templates if t["group"] in train_groups]
    return out


def candidates(action: str, t: dict, plan: dict) -> list[tuple[str, dict, dict]]:
    if "texts" in t:  # 바꿔 쓴 템플릿
        return bd.expand_paraphrase(t, plan, action)
    return bs.expand(t, plan, action)


def build_more(
    plan: dict, para: dict, train_groups: set[str], block: ba.Blocklist, total: int
) -> tuple[list[dict], Counter]:
    """더할 문장 `total`개와, 뺀 문장 수(이유별)."""
    rng = random.Random(plan.get("seed", 0) + 15)
    dropped: Counter = Counter()
    seen: set[str] = set()
    queues = []
    for action, t in train_templates(plan, para, train_groups):
        items = []
        for sentence, output, slots in candidates(action, t, plan):
            sentence = normalize(sentence)
            key = bs.compact(sentence)
            if key in seen:
                continue
            seen.add(key)
            why = block.reason(sentence)
            if why:
                dropped[why] += 1
                continue
            items.append((sentence, output, slots))
        if items:
            queues.append((action, t, bs.balanced(items, rng)))

    records: list[dict] = []
    while len(records) < total and any(items for _, _, items in queues):
        for _action, t, items in queues:
            if len(records) >= total:
                break
            if not items:
                continue
            sentence, output, _ = items.pop(0)
            meta = {
                "template_id": t["id"],
                "group": t.get("group", t["id"]),
                "tone": t["tone"],
                "source": "more",
                "indirect": bool(t.get("indirect")),
                "split": "train",
            }
            context = copy.deepcopy(rng.choice(plan["contexts"]["normal"]))
            records.append(bs.record(sentence, output, context, meta))
    return records, dropped


def main() -> int:
    parser = argparse.ArgumentParser(description="train 템플릿에서 문장을 더 뽑는다 (train 전용)")
    parser.add_argument(
        "--total", type=int, default=None, help="더할 문장 수 (기본: variety_v1.jsonl과 같은 수)"
    )
    parser.add_argument("--out", type=pathlib.Path, default=bs.OUT_DIR / f"more_{VERSION}.jsonl")
    args = parser.parse_args()

    total = args.total if args.total is not None else len(load(VARIETY))
    plan = yaml.safe_load(bs.SHEET.read_text(encoding="utf-8"))
    para = yaml.safe_load(bd.PARA_SHEET.read_text(encoding="utf-8"))
    train_groups = {
        r["meta"].get("group") or r["meta"]["template_id"]
        for r in load(ba.BASE_SPLIT / "train.jsonl")
    }
    block = ba.make_blocklist(extra_train=(AUGMENT,))
    try:
        records, dropped = build_more(plan, para, train_groups, block, total)
    except bs.SheetError as e:
        print(f"시트 오류: {e}", file=sys.stderr)
        return 1
    bs.write_jsonl(args.out, records)
    actions = Counter(r["output"]["action"] for r in records)
    print(f"더 뽑기 {len(records)}건 (목표 {total}) → {args.out}")
    print("  Action: " + ", ".join(f"{a} {n}" for a, n in actions.items()))
    print(
        f"  뺀 문장: val·test·STT 대본·train·보강과 같음 {dropped['same']}, "
        f"val·test·STT 대본과 비슷함 {dropped['similar']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
