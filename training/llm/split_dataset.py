"""LLM 데이터 분할 (LLM-05, 발표 p.9 ⑥): 가족(meta.group) 단위 Train/Val/Test + 캘리브레이션.

python -m training.llm.split_dataset   # → data/llm/split_v1/{train,val,test,calib}.jsonl

- 같은 가족(부모 템플릿과 그 Paraphrase)은 같은 split에 간다
  → 비슷한 문장이 train·test에 같이 안 들어간다.
- Action별로 따로 가족을 배정해 각 split의 문장 수가 비율(70/15/15%)에 가깝게 한다
  (큰 가족부터, 목표보다 가장 모자란 split에). Hard Negative는 범주별로 같은 방식.
- Test는 고정한다: 데이터를 다시 만들어도 같은 가족은 같은 split에 가도록 순서·seed를 고정.
- 캘리브레이션(양자화용)은 Train에서만, Action 비율대로 뽑는다 (학교 특강 규칙).
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import random
import sys
from collections import Counter, defaultdict

from training.llm import build_seed as bs

SPLITS = ("train", "val", "test")
RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}
CALIB_SIZE = 500  # 특강 권장 300~1,000


def load(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def group_key(record: dict) -> str:
    m = record["meta"]
    return m.get("group") or m["template_id"]


def stratum(record: dict) -> str:
    """분할 비율을 맞추는 묶음: 일반 데이터는 Action, Hard Negative는 범주 + Guard 기대 판정.

    기대 판정까지 나눠야 "Guard가 거절해야 할 위험 명령"이 test에도 들어가 Unsafe를 잴 수 있다.
    """
    m = record["meta"]
    if m["source"] == "hard_negative":
        return f"hn:{m['category']}:{m.get('expect_guard') or '-'}"
    return record["output"]["action"]


def assign_groups(records: list[dict], seed: int = 0) -> dict[str, str]:
    """가족 → split. 묶음(stratum)마다 큰 가족부터 목표 대비 가장 모자란 split에 넣고,
    이 묶음이 하나도 없는 split이 있으면 가장 남는 split의 가장 작은 가족을 옮긴다."""
    sizes: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        sizes[stratum(r)][group_key(r)] += 1
    rng = random.Random(seed)
    assignment: dict[str, str] = {}
    for st in sorted(sizes):
        groups = sorted(sizes[st].items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(n for _, n in groups)
        filled = Counter()
        mine = []  # 이 묶음에서 새로 배정한 가족
        for group, n in groups:
            if group in assignment:  # 다른 묶음에서 이미 배정 (같은 가족은 한 곳에)
                filled[assignment[group]] += n
                continue
            deficits = {sp: RATIOS[sp] * total - filled[sp] for sp in SPLITS}
            best = max(deficits.values())
            split = rng.choice(sorted(sp for sp, d in deficits.items() if d == best))
            assignment[group] = split
            filled[split] += n
            mine.append((group, n))
        for empty in [sp for sp in SPLITS if filled[sp] == 0]:
            # 가족이 2개 이상인 split 중 목표보다 가장 남는 곳에서 가장 작은 가족을 옮긴다
            donors = [sp for sp in SPLITS if sum(assignment[g] == sp for g, _ in mine) >= 2]
            if not donors:
                continue
            donor = max(donors, key=lambda sp: filled[sp] - RATIOS[sp] * total)
            movable = [(g, n) for g, n in mine if assignment[g] == donor]
            g, n = min(movable, key=lambda gn: (gn[1], gn[0]))
            assignment[g] = empty
            filled[donor] -= n
            filled[empty] += n
    return assignment


def split_records(records: list[dict], assignment: dict[str, str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {s: [] for s in SPLITS}
    for r in records:
        r = copy.deepcopy(r)
        r["meta"]["split"] = assignment[group_key(r)]
        out[r["meta"]["split"]].append(r)
    return out


def calibration(train: list[dict], size: int = CALIB_SIZE, seed: int = 0) -> list[dict]:
    """Train에서 Action 비율대로 뽑는다 (Hard Negative 제외 — 평소 입력 분포를 따르게)."""
    pool = [r for r in train if r["meta"]["source"] != "hard_negative"]
    by_action: dict[str, list[dict]] = defaultdict(list)
    for r in pool:
        by_action[r["output"]["action"]].append(r)
    rng = random.Random(seed)
    out = []
    for action in sorted(by_action):
        items = sorted(by_action[action], key=lambda r: bs.compact(r["instruction"]))
        k = round(size * len(items) / len(pool))
        out += rng.sample(items, min(k, len(items)))
    return out


def leaks(splits: dict[str, list[dict]]) -> list[str]:
    """두 split에 걸친 가족·같은 문장(띄어쓰기 무시, 맥락까지 같은 것) 목록."""
    problems = []
    seen_group: dict[str, str] = {}
    seen_text: dict[tuple, str] = {}
    for s, rows in splits.items():
        for r in rows:
            g = group_key(r)
            if seen_group.setdefault(g, s) != s:
                problems.append(f"가족 {g}: {seen_group[g]} / {s}")
            key = (bs.compact(r["instruction"]), json.dumps(r["context"], sort_keys=True))
            if seen_text.setdefault(key, s) != s:
                problems.append(f"문장 «{r['instruction']}»: {seen_text[key]} / {s}")
    return problems


def summary(splits: dict[str, list[dict]], calib: list[dict]) -> str:
    lines = ["| split | 전체 | 일반 | Hard Negative | 가족 |", "|---|---|---|---|---|"]
    for s in SPLITS:
        rows = splits[s]
        hn = sum(r["meta"]["source"] == "hard_negative" for r in rows)
        groups = len({group_key(r) for r in rows})
        lines.append(f"| {s} | {len(rows)} | {len(rows) - hn} | {hn} | {groups} |")
    lines.append(f"\n캘리브레이션: {len(calib)}건 (train에서)")
    actions = sorted({r["output"]["action"] for rows in splits.values() for r in rows})
    lines.append("\n| Action | " + " | ".join(SPLITS) + " |")
    lines.append("|---|---|---|---|")
    for a in actions:
        cells = [str(sum(r["output"]["action"] == a for r in splits[s])) for s in SPLITS]
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 데이터를 가족 단위로 Train/Val/Test로 나눈다")
    parser.add_argument("--dataset", type=pathlib.Path, default=bs.OUT_DIR / "dataset_v1.jsonl")
    parser.add_argument("--hard", type=pathlib.Path, default=bs.OUT_DIR / "hard_negative_v1.jsonl")
    parser.add_argument("--out-dir", type=pathlib.Path, default=bs.OUT_DIR / "split_v1")
    parser.add_argument("--calib-size", type=int, default=CALIB_SIZE)
    args = parser.parse_args()

    records = load(args.dataset) + load(args.hard)
    assignment = assign_groups(records)
    splits = split_records(records, assignment)
    problems = leaks(splits)
    if problems:
        print("누수:\n  " + "\n  ".join(problems[:20]), file=sys.stderr)
        return 1
    calib = calibration(splits["train"], args.calib_size)
    for s, rows in splits.items():
        bs.write_jsonl(args.out_dir / f"{s}.jsonl", rows)
    bs.write_jsonl(args.out_dir / "calib.jsonl", calib)
    (args.out_dir / "groups.json").write_text(
        json.dumps(dict(sorted(assignment.items())), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(summary(splits, calib))
    return 0


if __name__ == "__main__":
    sys.exit(main())
