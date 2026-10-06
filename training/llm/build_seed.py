"""기획 시트 → LLM Seed(LLM-02)·Hard Negative(LLM-03) 데이터 생성.

python -m training.llm.build_seed            # → data/llm/seed_v2.jsonl, hard_negative_v2.jsonl
python -m training.llm.build_seed --review-csv review.csv   # 사람 검수용 표 (Excel로 열기)

- 정답은 템플릿에서 정해지므로 사람이 문장마다 라벨을 붙이지 않는다. 검수는 "문장이 자연스러운가,
  정답이 맞는가"만 본다.
- 한 줄 = interfaces §3.4 형식 {instruction, context, output, meta}. split은 LLM-05에서 정한다.
- STT 테스트 대본(data/stt/script.csv)과 같은 문장은 넣지 않는다
  (STT→Action 평가가 부풀려지지 않게).
- 슬롯 값(장치·세기·시간)은 돌아가며 고르게 뽑는다. 부르는 말이 많은 장치가 더 많이 나오지 않게.
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

from common.function_call import DEVICES, PARAMS, TARGETS, TIMER_TARGETS, to_tokens, validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
SHEET = pathlib.Path(__file__).with_name("plan_sheet.yaml")
STT_SCRIPT = ROOT / "data/stt/script.csv"
OUT_DIR = ROOT / "data/llm"
WAKE = "자비스"
NO_PARTICLE = {"전부", "다", "모두", "전체"}  # "전부를 꺼 주세요"는 어색하다
_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")

VERSION = "v2"  # 지금 시트가 만드는 데이터 버전 (v1은 스키마 v0.1 때의 고정본)

# 템플릿에 devices가 없을 때 target 슬롯에 쓰는 장치 = 그 Action이 받는 전부 (interfaces §3.1)
DEFAULT_DEVICES = {
    "TURN_ON": DEVICES,
    "SET_LEVEL": DEVICES,
    "SET_TIMER": TIMER_TARGETS,
    "CANCEL_TIMER": TIMER_TARGETS,
}
ALL_TARGETS = TARGETS


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


def level_phrases(sheet: dict, target: str | None) -> dict:
    """그 장치의 세기를 부르는 말. 조명(밝기)·음악(음량)처럼 달리 말하는 장치는 device_levels에."""
    return sheet.get("device_levels", {}).get(target) or sheet["levels"]


def expand(template: dict, sheet: dict, action: str | None = None) -> list[tuple[str, dict, dict]]:
    """템플릿 하나 → (문장, 정답, 슬롯) 목록 (모든 조합)."""
    text = template["text"]
    # 문장에 장치가 없어도 정답·맥락이 장치를 쓰면 펼친다 ("그거 꺼줘" + last_target)
    refs = text + json.dumps(template["output"]) + str(template.get("last_target", ""))
    device_parts: list[dict[str, Any]] = [{}]
    if "{device" in refs:
        devices = template.get("devices") or DEFAULT_DEVICES.get(action or "", ALL_TARGETS)
        device_parts = [
            {"device": target, "_device": phrase, "_device_obj": with_object_particle(phrase)}
            for target in devices
            for phrase in sheet["devices"][target]
        ]
    time_parts: list[dict[str, Any]] = [{}]
    if "{time}" in text:
        time_parts = [{"time": int(t), "_time": p} for t, ps in sheet["times"].items() for p in ps]

    out = []
    for device in device_parts:
        level_parts: list[dict[str, Any]] = [{}]
        if "{level}" in text:
            # 세기를 부르는 말은 장치를 따른다 (문장에 장치가 없으면 정답의 target: "볼륨 {level}")
            target = device.get("device") or template["output"].get("target")
            level_parts = [
                {"level": int(lv), "_level": p}
                for lv, ps in level_phrases(sheet, target).items()
                for p in ps
            ]
        for level, time in itertools.product(level_parts, time_parts):
            slots: dict[str, Any] = {**device, **level, **time}
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


def _round_robin(groups: list[list]) -> list:
    return [x for row in itertools.zip_longest(*groups) for x in row if x is not None]


def balanced(items: list[tuple[str, dict, dict]], rng: random.Random) -> list:
    """뽑는 순서: 섞은 뒤 장치를 돌아가며, 같은 장치 안에서는 세기·시간을 돌아가며 하나씩.

    그냥 섞으면 부르는 말이 많은 장치(화구 6개 표현)가 적은 장치(선풍기 2개)보다 3배 많이 뽑힌다.
    """
    items = list(items)
    rng.shuffle(items)
    by_device: dict[Any, dict[Any, list]] = {}
    for item in items:
        slots = item[2]
        cell = (slots.get("level"), slots.get("time"))
        by_device.setdefault(slots.get("device"), {}).setdefault(cell, []).append(item)
    return _round_robin([_round_robin(list(cells.values())) for cells in by_device.values()])


def stt_script_sentences(path: pathlib.Path) -> set[str]:
    """STT 테스트 대본 문장 (호출어를 뺀 형태, 띄어쓰기·문장부호 무시)."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        texts = [row["text"] for row in csv.DictReader(f)]
    return {compact(t.removeprefix(WAKE).removeprefix("야")) for t in texts if t.startswith(WAKE)}


def record(sentence, output, context, meta) -> dict:
    return {"instruction": sentence, "context": context, "output": output, "meta": meta}


def pick(
    pools: list[tuple[dict, list]], need: int, seen: set[str] | None = None
) -> list[tuple[dict, tuple[str, dict, dict]]]:
    """템플릿별 후보에서 `need`개를 뽑는다.

    정답의 (장치, 세기) 칸을 돌아가며, 칸 안에서는 템플릿을 돌아가며 하나씩 뽑는다.
    템플릿만 돌아가며 뽑으면 한 장치만 다루는 템플릿이 많은 장치(음악: "볼륨…", "소리…")가
    다른 장치의 몇 배가 된다.
    칸 안에서는 문장이 적은 템플릿부터 뽑는다 — 문장이 하나뿐인 간접 발화
    ("손님이 어둡대 조명 밝게 해줘")가 슬롯 템플릿에 밀려 빠지지 않게.
    `seen`(띄어쓰기를 지운 문장)에 있는 문장은 건너뛰고, 뽑은 문장을 `seen`에 더한다.
    """
    cells: dict[tuple, list[tuple[dict, list]]] = {}
    for template, items in pools:
        by_cell: dict[tuple, list] = {}
        for item in items:
            by_cell.setdefault((item[1].get("target"), item[1].get("level")), []).append(item)
        for cell, cell_items in by_cell.items():
            cells.setdefault(cell, []).append((template, cell_items))
    for queues in cells.values():
        queues.sort(key=lambda q: len(q[1]))  # 안정 정렬: 수가 같으면 시트 순서
    picked: list[tuple[dict, tuple[str, dict, dict]]] = []
    turn = dict.fromkeys(cells, 0)  # 칸마다 다음에 뽑을 템플릿
    while len(picked) < need and any(items for queues in cells.values() for _, items in queues):
        for cell, queues in cells.items():
            if len(picked) >= need:
                break
            for _ in range(len(queues)):
                template, items = queues[turn[cell] % len(queues)]
                turn[cell] += 1
                while items and seen is not None and compact(items[0][0]) in seen:
                    items.pop(0)
                if items:
                    item = items.pop(0)
                    if seen is not None:
                        seen.add(compact(item[0]))
                    picked.append((template, item))
                    break
    return picked


def build_seed(sheet: dict, exclude: set[str]) -> tuple[list[dict], dict[str, int]]:
    """Action별 목표 수량만큼 장치·세기와 템플릿을 고르게 돌아가며 뽑는다."""
    rng = random.Random(sheet.get("seed", 0))
    records, shortfall = [], {}
    for action, target in sheet["targets"].items():
        if action not in PARAMS:
            raise SheetError(f"targets의 모르는 Action: {action}")
        pools = []
        for t in sheet["templates"].get(action, []):
            items = [it for it in expand(t, sheet, action) if compact(it[0]) not in exclude]
            pools.append((t, balanced(items, rng)))
        chosen = pick(pools, target)
        for t, (sentence, output, _) in chosen:
            context = copy.deepcopy(rng.choice(sheet["contexts"]["normal"]))
            meta = {
                "template_id": t["id"],
                "tone": t["tone"],
                "source": "seed",
                "indirect": bool(t.get("indirect")),
                "split": None,
            }
            records.append(record(sentence, output, context, meta))
        if len(chosen) < target:
            shortfall[action] = target - len(chosen)
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
            for sentence, output, slots in balanced(items, rng)[:cap]:
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
    parser.add_argument("--version", default=VERSION)
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
