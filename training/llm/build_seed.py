"""기획 시트 → LLM Seed(LLM-02)·Hard Negative(LLM-03) 데이터 생성.

python -m training.llm.build_seed            # → data/llm/seed_v1.jsonl, hard_negative_v1.jsonl
python -m training.llm.build_seed --review-csv review.csv   # 사람 검수용 표 (Excel로 열기)

- 정답은 템플릿에서 정해지므로 사람이 문장마다 라벨을 붙이지 않는다. 검수는 "문장이 자연스러운가,
  정답이 맞는가"만 본다.
- 한 줄 = interfaces §3.4 형식 {instruction, context, output, meta}. split은 LLM-05에서 정한다.
- STT 테스트 대본(data/stt/script.csv)과 같은 문장은 넣지 않는다
  (STT→Action 평가가 부풀려지지 않게).
"""

from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import pathlib
import random
import re
import sys
from collections import Counter
from typing import Any

import yaml

from common.function_call import PARAMS, to_tokens, validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHEET = pathlib.Path(__file__).with_name("plan_sheet.yaml")
STT_SCRIPT = ROOT / "data/stt/script.csv"
OUT_DIR = ROOT / "data/llm"
WAKE = "자비스"
NO_PARTICLE = {"전부", "다", "모두", "전체"}  # "전부를 꺼 주세요"는 어색하다
_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")

# Action별로 target 슬롯에 쓸 수 있는 장치 (interfaces §3.1)
DEFAULT_DEVICES = {
    "TURN_ON": ["hood", "burner_1", "burner_2"],
    "SET_LEVEL": ["hood", "burner_1", "burner_2"],
}
ALL_TARGETS = ["hood", "burner_1", "burner_2", "all"]


class SheetError(ValueError):
    """기획 시트 오류 (슬롯 이름, 정답 스키마 등)."""


def compact(text: str) -> str:
    return _NOT_WORD.sub("", text)


def with_object_particle(phrase: str) -> str:
    if phrase in NO_PARTICLE:
        return phrase
    last = phrase[-1]
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return phrase + ("을" if has_final else "를")


def _fill(value: Any, slots: dict[str, Any]) -> Any:
    """정답 안의 "{device}" 같은 자리를 슬롯 값(정수·문자열)으로 바꾼다."""
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        key = value[1:-1]
        if key not in slots:
            raise SheetError(f"정답의 {value}에 해당하는 슬롯이 없음")
        return slots[key]
    if isinstance(value, dict):
        return {k: _fill(v, slots) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, slots) for v in value]
    return value


def expand(template: dict, sheet: dict, action: str | None = None) -> list[tuple[str, dict, dict]]:
    """템플릿 하나 → (문장, 정답, 슬롯) 목록 (모든 조합)."""
    text = template["text"]
    # 문장에 장치가 없어도 정답·맥락이 장치를 쓰면 펼친다 ("그거 꺼줘" + last_target)
    refs = text + json.dumps(template["output"]) + str(template.get("last_target", ""))
    uses_device = "{device" in refs
    axes: list[list[dict[str, Any]]] = []
    if uses_device:
        devices = template.get("devices") or DEFAULT_DEVICES.get(action or "", ALL_TARGETS)
        axes.append(
            [
                {"device": target, "_device": phrase, "_device_obj": with_object_particle(phrase)}
                for target in devices
                for phrase in sheet["devices"][target]
            ]
        )
    if "{level}" in text:
        axes.append(
            [{"level": int(lv), "_level": p} for lv, ps in sheet["levels"].items() for p in ps]
        )
    if "{time}" in text:
        axes.append([{"time": int(t), "_time": p} for t, ps in sheet["times"].items() for p in ps])

    out = []
    for combo in itertools.product(*axes) if axes else [()]:
        slots: dict[str, Any] = {}
        for part in combo:
            slots.update(part)
        sentence = (
            text.replace("{device_obj}", slots.get("_device_obj", ""))
            .replace("{device}", slots.get("_device", ""))
            .replace("{level}", slots.get("_level", ""))
            .replace("{time}", slots.get("_time", ""))
        )
        if "{" in sentence:
            raise SheetError(f"{template['id']}: 채우지 못한 슬롯 — {sentence}")
        try:
            output = _fill(template["output"], slots)
        except SheetError as e:
            raise SheetError(f"{template['id']}: {e}") from e
        try:
            validate(output)
        except ValueError as e:
            raise SheetError(f"{template['id']} «{sentence}»: {e}") from e
        out.append((sentence, output, slots))
    return out


def stt_script_sentences(path: pathlib.Path) -> set[str]:
    """STT 테스트 대본 문장 (호출어를 뺀 형태, 띄어쓰기·문장부호 무시)."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        texts = [row["text"] for row in csv.DictReader(f)]
    return {compact(t.removeprefix(WAKE).removeprefix("야")) for t in texts if t.startswith(WAKE)}


def record(sentence, output, context, meta) -> dict:
    return {"instruction": sentence, "context": context, "output": output, "meta": meta}


def build_seed(sheet: dict, exclude: set[str]) -> tuple[list[dict], dict[str, int]]:
    """Action별 목표 수량만큼 템플릿을 고르게 돌아가며 뽑는다."""
    rng = random.Random(sheet.get("seed", 0))
    records, shortfall = [], {}
    for action, target in sheet["targets"].items():
        if action not in PARAMS:
            raise SheetError(f"targets의 모르는 Action: {action}")
        pools = []
        for t in sheet["templates"].get(action, []):
            items = [it for it in expand(t, sheet, action) if compact(it[0]) not in exclude]
            rng.shuffle(items)
            pools.append((t, items))
        picked = 0
        while picked < target and any(items for _, items in pools):
            for t, items in pools:
                if items and picked < target:
                    sentence, output, _ = items.pop()
                    context = copy.deepcopy(rng.choice(sheet["contexts"]["normal"]))
                    meta = {
                        "template_id": t["id"],
                        "tone": t["tone"],
                        "source": "seed",
                        "indirect": bool(t.get("indirect")),
                        "split": None,
                    }
                    records.append(record(sentence, output, context, meta))
                    picked += 1
        if picked < target:
            shortfall[action] = target - picked
    return dedupe(records), shortfall


def build_hard_negatives(sheet: dict, exclude: set[str]) -> list[dict]:
    rng = random.Random(sheet.get("seed", 0) + 1)
    cap = sheet.get("hard_negative_max_per_template", 8)
    records = []
    for category, templates in sheet["hard_negatives"].items():
        for t in templates:
            items = [
                it
                for it in expand(t, sheet, t["output"]["action"])
                if compact(it[0]) not in exclude
            ]
            rng.shuffle(items)
            for sentence, output, slots in items[:cap]:
                pool = sheet["contexts"][t.get("context", "normal")]
                context = copy.deepcopy(rng.choice(pool))
                if "last_target" in t:
                    context["last_target"] = _fill(t["last_target"], slots)
                meta = {
                    "template_id": t["id"],
                    "category": category,
                    "source": "hard_negative",
                    "expect_guard": t.get("expect_guard"),
                    "note": t.get("note"),
                    "split": None,
                }
                records.append(record(sentence, output, context, meta))
    return dedupe(records)


def dedupe(records: list[dict]) -> list[dict]:
    """같은 문장·같은 맥락이 두 번 나오면 하나만. 정답이 다르면 시트 오류."""
    seen: dict[tuple, dict] = {}
    out = []
    for r in records:
        key = (compact(r["instruction"]), json.dumps(r["context"], sort_keys=True))
        if key in seen:
            if seen[key]["output"] != r["output"]:
                raise SheetError(
                    f"같은 문장인데 정답이 다름: «{r['instruction']}» "
                    f"{seen[key]['meta']['template_id']} vs {r['meta']['template_id']}"
                )
            continue
        seen[key] = r
        out.append(r)
    return out


def write_jsonl(path: pathlib.Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_review_csv(path: pathlib.Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # Excel이 한글을 읽게 BOM
        w = csv.writer(f)
        w.writerow(
            [
                "instruction",
                "정답(함수 토큰)",
                "template_id",
                "tone/category",
                "state",
                "last_target",
                "expect_guard",
                "검수(OK/수정)",
                "메모",
            ]
        )
        for r in records:
            m = r["meta"]
            w.writerow(
                [
                    r["instruction"],
                    to_tokens(r["output"]),
                    m["template_id"],
                    m.get("tone") or m.get("category"),
                    r["context"]["state"],
                    r["context"]["last_target"] or "",
                    m.get("expect_guard") or "",
                    "",
                    "",
                ]
            )


def summary(seed: list[dict], hard: list[dict]) -> str:
    lines = [f"Seed {len(seed)}건"]
    by_action = Counter(r["output"]["action"] for r in seed)
    lines.append("  Action: " + ", ".join(f"{a} {n}" for a, n in by_action.items()))
    lines.append(
        "  어투: "
        + ", ".join(f"{t} {n}" for t, n in Counter(r["meta"]["tone"] for r in seed).items())
    )
    lines.append(
        f"  간접 발화 {sum(r['meta']['indirect'] for r in seed)}건, "
        f"템플릿 {len({r['meta']['template_id'] for r in seed})}개"
    )
    lines.append(f"Hard Negative {len(hard)}건")
    lines.append(
        "  "
        + ", ".join(f"{c} {n}" for c, n in Counter(r["meta"]["category"] for r in hard).items())
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="기획 시트로 LLM Seed·Hard Negative를 만든다")
    parser.add_argument("--sheet", type=pathlib.Path, default=SHEET)
    parser.add_argument("--out-dir", type=pathlib.Path, default=OUT_DIR)
    parser.add_argument("--version", default="v1")
    parser.add_argument(
        "--exclude-script",
        type=pathlib.Path,
        default=STT_SCRIPT,
        help="이 대본의 문장은 넣지 않음 (STT 테스트 세트)",
    )
    parser.add_argument("--review-csv", type=pathlib.Path, default=None, help="검수용 CSV")
    args = parser.parse_args()

    sheet = yaml.safe_load(args.sheet.read_text(encoding="utf-8"))
    exclude = stt_script_sentences(args.exclude_script)
    try:
        seed, shortfall = build_seed(sheet, exclude)
        hard = build_hard_negatives(sheet, exclude)
    except SheetError as e:
        print(f"기획 시트 오류: {e}", file=sys.stderr)
        return 1
    write_jsonl(args.out_dir / f"seed_{args.version}.jsonl", seed)
    write_jsonl(args.out_dir / f"hard_negative_{args.version}.jsonl", hard)
    print(summary(seed, hard))
    print(f"STT 대본과 같은 문장 제외: 대본 {len(exclude)}문장 기준")
    if shortfall:
        print(
            "목표보다 부족 (템플릿 조합이 모자람): "
            + ", ".join(f"{a} -{n}" for a, n in shortfall.items())
        )
    if args.review_csv:
        write_review_csv(args.review_csv, seed + hard)
        print(f"검수용 CSV: {args.review_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
