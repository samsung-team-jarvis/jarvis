"""Seed + Paraphrase → LLM 데이터 (LLM-04, 발표 p.9 ②~④).

python -m training.llm.build_dataset                          # → data/llm/dataset_v2.jsonl
python -m training.llm.build_dataset --review-csv review.csv  # Paraphrase 검수용 표

① Seed: plan_sheet.yaml (build_seed) — 모두 넣는다
② Paraphrase: paraphrase_sheet.yaml — 부모 템플릿의 정답·슬롯을 물려받은 바꿔 쓴 템플릿
③ 검증·중복 제거: 스키마 검증, 띄어쓰기·문장부호만 다른 중복 제거, 같은 문장에 다른 정답이면 실패
④ Entity 치환·STT 표기 정규화: 슬롯 채우기 + 서비스와 같은 STT 오인식 사전(normalize) 적용
   (⑤ Hard Negative는 hard_negative_v2.jsonl로 따로, ⑥ 분할은 LLM-05)
"""

from __future__ import annotations

import argparse
import copy
import itertools
import pathlib
import random
import re
import sys
from collections import Counter

import yaml

from services.llm_svc.stt_fixes import normalize
from training.llm import build_seed as bs

PARA_SHEET = pathlib.Path(__file__).with_name("paraphrase_sheet.yaml")
_CHOICE = re.compile(r"\(([^()]*\|[^()]*)\)")


def alternatives(text: str) -> list[str]:
    """ "(a|b) 켜(줘|줄래)" → 모든 조합. 선택지가 없으면 그대로 1개."""
    parts = _CHOICE.split(text)  # 짝수 칸: 고정 글자, 홀수 칸: 선택지 "a|b"
    options = [[p] if i % 2 == 0 else p.split("|") for i, p in enumerate(parts)]
    return ["".join(combo) for combo in itertools.product(*options)]


def find_template(plan: dict, template_id: str) -> tuple[str, dict]:
    for action, templates in plan["templates"].items():
        for t in templates:
            if t["id"] == template_id:
                return action, t
    raise bs.SheetError(f"paraphrase_sheet의 부모 템플릿이 plan_sheet에 없음: {template_id}")


def paraphrase_templates(plan: dict, para: dict) -> dict[str, list[dict]]:
    """Action → 바꿔 쓴 템플릿 목록. 정답·devices·indirect는 부모 것, 가족(group)은 부모 id.

    그 말투가 어울리는 장치가 부모보다 적으면 devices만 줄여 쓸 수 있다 ("음악 돌려"는 어색하다).
    """
    out: dict[str, list[dict]] = {}
    for parent_id, items in para["paraphrases"].items():
        action, parent = find_template(plan, parent_id)
        for i, item in enumerate(items, 1):
            t = copy.deepcopy(parent)
            t.update(id=f"{parent_id}_p{i}", tone=item["tone"], texts=alternatives(item["text"]))
            t["group"] = parent_id
            if "devices" in item:
                t["devices"] = item["devices"]
            out.setdefault(action, []).append(t)
    return out


def expand_paraphrase(t: dict, plan: dict, action: str) -> list[tuple[str, dict, dict]]:
    items = []
    for text in t["texts"]:
        items += bs.expand({**t, "text": text}, plan, action)
    return items


def _with_group(record: dict) -> dict:
    meta = record["meta"]
    meta.setdefault("group", meta["template_id"])
    return record


def _normalized(record: dict) -> dict:
    """④ 학습 입력도 서비스 입력과 같게 STT 오인식 사전을 거친다."""
    fixed = normalize(record["instruction"])
    if fixed != record["instruction"]:
        record["meta"]["raw_instruction"] = record["instruction"]
        record["instruction"] = fixed
    return record


def build_dataset(plan: dict, para: dict, exclude: set[str]) -> tuple[list[dict], dict[str, int]]:
    seed, _ = bs.build_seed(plan, exclude)
    seed = [_with_group(r) for r in seed]
    seen = {bs.compact(r["instruction"]) for r in seed}
    seed_count = Counter(r["output"]["action"] for r in seed)

    rng = random.Random(plan.get("seed", 0) + 2)
    records, shortfall = list(seed), {}
    templates = paraphrase_templates(plan, para)
    for action, target in para["targets"].items():
        pools = []
        for t in templates.get(action, []):
            items = [
                it
                for it in expand_paraphrase(t, plan, action)
                if bs.compact(it[0]) not in exclude and bs.compact(it[0]) not in seen
            ]
            pools.append((t, bs.balanced(items, rng)))
        need = target - seed_count[action]
        chosen = bs.pick(pools, need, seen)
        for t, (sentence, output, _) in chosen:
            context = copy.deepcopy(rng.choice(plan["contexts"]["normal"]))
            meta = {
                "template_id": t["id"],
                "group": t["group"],
                "tone": t["tone"],
                "source": "paraphrase",
                "indirect": bool(t.get("indirect")),
                "split": None,
            }
            records.append(bs.record(sentence, output, context, meta))
        if len(chosen) < need:
            shortfall[action] = need - len(chosen)
    records = bs.dedupe([_normalized(r) for r in records])
    return records, shortfall


def summary(records: list[dict]) -> str:
    by_source = Counter(r["meta"]["source"] for r in records)
    by_action = Counter(r["output"]["action"] for r in records)
    lines = [
        f"데이터 {len(records)}건 "
        f"(seed {by_source['seed']} · paraphrase {by_source['paraphrase']})",
        "  Action: " + ", ".join(f"{a} {n}" for a, n in by_action.items()),
        "  어투: "
        + ", ".join(f"{t} {n}" for t, n in Counter(r["meta"]["tone"] for r in records).items()),
        f"  가족(분할 단위) {len({r['meta']['group'] for r in records})}개, "
        f"템플릿 {len({r['meta']['template_id'] for r in records})}개, "
        f"간접 발화 {sum(r['meta']['indirect'] for r in records)}건",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed + Paraphrase로 LLM 데이터를 만든다")
    parser.add_argument("--plan", type=pathlib.Path, default=bs.SHEET)
    parser.add_argument("--para", type=pathlib.Path, default=PARA_SHEET)
    parser.add_argument("--out-dir", type=pathlib.Path, default=bs.OUT_DIR)
    parser.add_argument("--version", default=bs.VERSION)
    parser.add_argument("--exclude-script", type=pathlib.Path, default=bs.STT_SCRIPT)
    parser.add_argument(
        "--review-csv", type=pathlib.Path, default=None, help="Paraphrase 검수용 표"
    )
    args = parser.parse_args()

    plan = yaml.safe_load(args.plan.read_text(encoding="utf-8"))
    para = yaml.safe_load(args.para.read_text(encoding="utf-8"))
    try:
        records, shortfall = build_dataset(plan, para, bs.stt_script_sentences(args.exclude_script))
    except bs.SheetError as e:
        print(f"시트 오류: {e}", file=sys.stderr)
        return 1
    bs.write_jsonl(args.out_dir / f"dataset_{args.version}.jsonl", records)
    print(summary(records))
    if shortfall:
        print("목표보다 부족: " + ", ".join(f"{a} -{n}" for a, n in shortfall.items()))
    if args.review_csv:
        bs.write_review_csv(
            args.review_csv, [r for r in records if r["meta"]["source"] == "paraphrase"]
        )
        print(f"검수용 CSV (paraphrase만): {args.review_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
