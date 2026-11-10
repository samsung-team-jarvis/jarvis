"""LLM 출력 + 검증 실패 시 규칙 파서 대체(LLM-09)를 이미 낸 예측으로 잰다 (모델을 다시 돌리지 않음).

.venv-llm/bin/python -m bench.llm_eval --engine hf --model runs/llm/<모델> --finetuned \
    --split test --csv lora_test.csv
python -m bench.llm_fallback lora_test.csv --csv lora_fb_test.csv     # 표 + 대체 적용 CSV
python -m bench.llm_errors --counts-only lora_fb_test.csv             # 오류 유형 (test는 건수만)

llm_svc와 같은 함수(services.llm_svc.interpret.resolve)를 쓴다. 생성기 자리에 CSV의 LLM 출력
(`raw`)을 돌려주는 함수를 넣으므로 greedy 출력이면 서비스와 결과가 같다.
나오는 CSV는 llm_eval과 열이 같다. `raw`는 최종 명령의 함수 토큰, `valid`는 LLM 출력의 검증 통과
여부다.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys

from bench.llm_eval import CSV_COLUMNS
from common.function_call import parse_tokens, to_tokens
from services.llm_svc.interpret import resolve


def apply(rows: list[dict]) -> list[dict]:
    """각 행에 대체 경로를 적용한 결과 (`final`: 최종 명령, `fallback`: 규칙 파서로 대체했는가)."""
    out = []
    for r in rows:
        context = {"state": r["state"], "last_target": r["last_target"] or None}
        res = resolve(r["instruction"], context, lambda _t, _c, raw=r["raw"]: (raw, 0))
        expected = parse_tokens(r["expected"])
        out.append({**r, "final": res.call, "llm_valid": res.valid, "fallback": res.fallback,
                    "action_ok": res.call["action"] == expected["action"],
                    "entity_ok": res.call == expected})  # fmt: skip
    return out


def report(rows: list[dict], name: str) -> str:
    n = len(rows)

    def pct(k: int) -> str:
        return f"{k / n * 100:.1f}%"

    fb = [x for x in rows if x["fallback"]]
    action, entity = sum(x["action_ok"] for x in rows), sum(x["entity_ok"] for x in rows)
    return "\n".join(
        [
            f"### {name} + 규칙 파서 대체 (n={n})",
            "",
            "| Action Acc | Entity Acc | LLM Valid | 대체한 수 | 대체 후 전체 일치 |",
            "|---|---|---|---|---|",
            f"| {pct(action)} | {pct(entity)} "
            f"| {pct(sum(x['llm_valid'] for x in rows))} | {len(fb)} "
            f"| {sum(x['entity_ok'] for x in fb)} / {len(fb)} |",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 예측 CSV에 규칙 파서 대체를 적용해 잰다")
    parser.add_argument("csv", type=pathlib.Path, help="bench/llm_eval.py --csv 결과 (LLM)")
    parser.add_argument("--csv", dest="out", type=pathlib.Path, default=None, help="대체 적용 CSV")
    args = parser.parse_args()
    with args.csv.open(encoding="utf-8", newline="") as f:
        rows = apply(list(csv.DictReader(f)))
    print(report(rows, args.csv.stem))
    if args.out:
        with args.out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            w.writeheader()
            for x in rows:
                w.writerow({**x, "raw": to_tokens(x["final"]), "valid": x["llm_valid"],
                            "correct": x["entity_ok"]})  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
