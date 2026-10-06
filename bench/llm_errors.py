"""명령 해석 오류 유형 분류 (LLM-10): 예측 CSV(bench/llm_eval.py) → 유형별 건수·예시·틀린 가족.

python -m bench.llm_eval --engine rule --split val --csv rule_val.csv
python -m bench.llm_errors rule_val.csv lora_val.csv          # 여러 개를 나란히

**val로만 분석한다** (test는 비교할 때만 — docs/workflows/experiment.md).

틀린 예측 하나는 아래 유형 중 **하나**로만 센다 (위에서부터 먼저 맞는 것):

| 유형 | 뜻 |
|---|---|
| 형식 깨짐 | 함수 토큰 모양이 아니다 |
| 규칙 위반 | 모양은 맞는데 없는 함수·키·장치 이름(`target=alarm`)이거나 꼭 필요한 인자가 빠짐 |
| 빠진 값 채움 | 되물어야 하는데 값을 지어내 실행 (같은 함수) |
| 불필요한 되묻기 | 값이 다 있는데 되물음 |
| 지원 외를 실행 | 지원 외인데 다른 함수를 냄 |
| 지원 외로 거절 | 할 수 있는 명령인데 지원 외라고 함 |
| 다른 함수 | 그 밖에 함수가 다름 |
| 장치 틀림 | 함수는 같고 장치가 다름 |
| 값 틀림 | 함수·장치는 같고 세기·시간·빠진 항목이 다름 |

그와 별도로 겹쳐 세는 표시: 대명사 실패(Hard Negative `pronoun`), 긴급 정지 오판(정답이나 예측이
긴급 정지), 틀린 실행(장치·결제를 움직이는 함수를 냈는데 정답과 다름 — 안전과 관련된 오류).
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
from collections import Counter

from common.function_call import FunctionCallError, parse_tokens

TYPES = {
    "format": "형식 깨짐",
    "invented": "규칙 위반",
    "filled_missing": "빠진 값 채움",
    "needless_ask": "불필요한 되묻기",
    "unsupported_executed": "지원 외를 실행",
    "refused": "지원 외로 거절",
    "wrong_action": "다른 함수",
    "wrong_target": "장치 틀림",
    "wrong_value": "값 틀림",
}
FLAGS = {
    "pronoun": "대명사 실패",
    "emergency": "긴급 정지 오판",
    "wrong_execution": "틀린 실행",
}
# 장치·타이머·결제를 실제로 움직이는 함수 ("네"는 기다리던 명령을 실행시킨다)
EXEC_ACTIONS = {
    "TURN_ON",
    "TURN_OFF",
    "SET_LEVEL",
    "SET_TIMER",
    "CANCEL_TIMER",
    "EMERGENCY_STOP",
    "REQUEST_PAYMENT",
    "CONFIRM",
}
_TOKEN_SHAPE = re.compile(r"^\s*<jarvis_\d+>\(.*\)<jarvis_end>\s*$", re.DOTALL)


def _effective_action(call: dict) -> str:
    """되묻기면 하려던 함수 (빠진 값 채움을 가리려고)."""
    return call.get("for_action") or call["action"]


def classify(expected: dict, raw: str) -> str | None:
    """틀린 예측의 유형 (TYPES 키). 맞으면 None."""
    if not _TOKEN_SHAPE.match(raw or ""):
        return "format"
    try:
        pred = parse_tokens(raw)
    except FunctionCallError:
        return "invented"
    if pred == expected:
        return None
    e_act, p_act = expected["action"], pred["action"]
    if e_act == "ASK_CLARIFY" and p_act != "ASK_CLARIFY":
        if expected["for_action"] == p_act:
            return "filled_missing"
    if e_act != "ASK_CLARIFY" and p_act == "ASK_CLARIFY":
        return "needless_ask"
    if e_act == "UNSUPPORTED":
        return "unsupported_executed"
    if p_act == "UNSUPPORTED":
        return "refused"
    if _effective_action(expected) != _effective_action(pred) or e_act != p_act:
        return "wrong_action"
    if expected.get("target") != pred.get("target"):
        return "wrong_target"
    return "wrong_value"


def flags(expected: dict, raw: str, category: str) -> set[str]:
    try:
        pred = parse_tokens(raw)
    except FunctionCallError:
        pred = None
    if pred == expected:
        return set()
    out = set()
    if category == "pronoun":
        out.add("pronoun")
    actions = {expected["action"], pred["action"] if pred else None}
    if "EMERGENCY_STOP" in actions:
        out.add("emergency")
    if pred and pred["action"] in EXEC_ACTIONS:
        out.add("wrong_execution")
    return out


def load(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def analyze(rows: list[dict]) -> dict:
    types: Counter = Counter()
    marks: Counter = Counter()
    families: Counter = Counter()
    examples: dict[str, list[str]] = {}
    for r in rows:
        expected = parse_tokens(r["expected"])
        kind = classify(expected, r["raw"])
        if kind is None:
            continue
        types[kind] += 1
        marks.update(flags(expected, r["raw"], r.get("category", "")))
        families[r.get("group") or "-"] += 1
        examples.setdefault(kind, [])
        if len(examples[kind]) < 3:
            examples[kind].append(f"«{r['instruction']}» {r['expected']} → {r['raw'].strip()[:60]}")
    return {"n": len(rows), "errors": sum(types.values()), "types": types, "flags": marks,
            "families": families, "examples": examples}  # fmt: skip


def report(results: dict[str, dict], top: int = 10) -> str:
    names = list(results)
    lines = ["| 유형 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines.append(
        "| **틀린 수 / 전체** | "
        + " | ".join(f"**{r['errors']} / {r['n']}**" for r in results.values())
        + " |"
    )
    for key, label in TYPES.items():
        lines.append(
            f"| {label} | " + " | ".join(str(r["types"][key]) for r in results.values()) + " |"
        )
    for key, label in FLAGS.items():
        lines.append(
            f"| (겹쳐 셈) {label} | "
            + " | ".join(str(r["flags"][key]) for r in results.values())
            + " |"
        )
    for name, r in results.items():
        lines += ["", f"### {name}", "", "많이 틀린 가족: "
                  + ", ".join(f"`{g}` {n}" for g, n in r["families"].most_common(top))]  # fmt: skip
        for key, label in TYPES.items():
            for ex in r["examples"].get(key, []):
                lines.append(f"- {label}: {ex}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="명령 해석 예측 CSV의 오류를 유형별로 센다")
    parser.add_argument("csv", nargs="+", type=pathlib.Path, help="bench/llm_eval.py --csv 결과")
    parser.add_argument("--top", type=int, default=10, help="많이 틀린 가족을 몇 개 보일지")
    args = parser.parse_args()
    results = {path.stem: analyze(load(path)) for path in args.csv}
    print(report(results, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
