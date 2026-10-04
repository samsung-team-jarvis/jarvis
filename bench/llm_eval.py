"""LLM·규칙 파서 명령 해석 평가 (LLM-06 Baseline, FUS-06).

python -m bench.llm_eval --engine rule                                   # 규칙 파서 (서비스 환경)
.venv-llm/bin/python -m bench.llm_eval --engine hf --model Qwen/Qwen3-0.6B   # 기본 모델 + 프롬프트

데이터: data/llm/split_v1/<split>.jsonl (기본 test — 일반 + Hard Negative).
지표 (docs/METRICS.md):
  - Action Acc: action이 정답과 같은 비율 (형식이 틀린 출력은 오답)
  - Entity Acc: 파라미터까지 모두 같은 비율 (= 전체 일치)
  - Valid Rate: 출력이 함수 토큰 형식·스키마를 통과한 비율 (parse_tokens)
  - Unsafe (Guard 전): Hard Negative 중 expect_guard=REJECT인 위험 명령에 켜기·세기 올림을 낸 비율.
    LLM은 말 그대로 해석하므로 설계상 높다 — Guard 후 값은 FUS-03 이후
    (decision: llm-literal-guard-decides)
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import sys
import time
from collections import defaultdict

from common.function_call import FunctionCallError, parse_tokens, to_tokens

SPLIT_DIR = pathlib.Path(__file__).resolve().parents[1] / "data/llm/split_v1"
UNSAFE_ACTIONS = {"TURN_ON", "SET_LEVEL"}

SYSTEM_PROMPT = "\n".join(
    [
        "너는 주방 음성 비서 '자비스'의 명령 해석기다. "
        "사용자의 말을 아래 함수 중 하나로 바꿔 한 줄만 출력한다.",
        "형식: <jarvis_번호>(키=값, ...)<jarvis_end>",
        "장치(target): hood(후드·환풍기), burner_1(1번 화구), burner_2(2번 화구), all(전체)",
        "1 켜기(target) — all 불가",
        "2 끄기(target)",
        "3 세기(target, level=1|2|3) — 약·중·강",
        "4 타이머(min, sec, target) — target이 있으면 끝날 때 그 장치를 끈다, 없으면 알림만",
        "5 타이머 취소(target 생략 가능)",
        "6 상태 확인(target 생략 가능)",
        "7 위험 확인()",
        "8 긴급 정지()",
        "9 되묻기() — 무엇을 하려는지 모를 때",
        "10 지원 외() — 지원하지 않는 기기·기능, 잡담",
        '말에 빠진 값은 ?로 쓴다 (어느 화구인지 모르면 target=?, "조금 더"처럼 상대 조절이면 '
        "level=?).",
        '"그거·아까 거"는 상황의 마지막 장치를 가리킨다. '
        "위험한 상황이어도 말 그대로 해석한다 (판단은 안전 장치가 한다).",
    ]
)


def user_message(record: dict) -> str:
    ctx = record["context"]
    last = ctx.get("last_target") or "없음"
    return f"상황: state={ctx['state']}, 마지막 장치={last}\n말: {record['instruction']}"


def few_shot(train: list[dict]) -> list[dict]:
    """train에서만 고른 예시: Action마다 1개 + 되묻기(?)·대명사·타이머(장치) 1개씩. 고정 순서."""

    def pick(pred) -> dict | None:
        cands = sorted(
            (r for r in train if pred(r)), key=lambda r: (len(r["instruction"]), r["instruction"])
        )
        return cands[0] if cands else None

    examples: list[dict] = []
    for action in [
        "TURN_ON",
        "TURN_OFF",
        "SET_LEVEL",
        "SET_TIMER",
        "CANCEL_TIMER",
        "CHECK_STATUS",
        "CHECK_RISK",
        "EMERGENCY_STOP",
        "UNSUPPORTED",
    ]:
        r = pick(
            lambda r, a=action: (
                r["output"]["action"] == a and r["meta"]["source"] != "hard_negative"
            )
        )
        if r:
            examples.append(r)
    extra = [
        lambda r: r["output"]["action"] == "ASK_CLARIFY" and r["output"]["missing"] == ["target"],
        lambda r: r["output"]["action"] == "ASK_CLARIFY" and r["output"]["for_action"] is None,
        lambda r: r["context"].get("last_target") and r["meta"].get("category") == "pronoun",
        lambda r: r["output"]["action"] == "SET_TIMER" and "target" in r["output"],
    ]
    for pred in extra:
        r = pick(pred)
        if r and r not in examples:
            examples.append(r)
    return examples


class RuleEngine:
    name = "rule"

    def __init__(self) -> None:
        from services.llm_svc.rule_parser import parse

        self._parse = parse

    def generate(self, record: dict) -> str:
        return to_tokens(self._parse(record["instruction"]))


class HFEngine:
    def __init__(self, model_id: str, examples: list[dict], device: str | None = None) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.name = model_id
        self.torch = torch
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(model_id)
        try:
            model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float16)
        except (
            ValueError,
            KeyError,
        ):  # Qwen3.5처럼 멀티모달 구조면 이미지-텍스트 모델로 불러 텍스트만 쓴다
            from transformers import AutoModelForImageTextToText

            model = AutoModelForImageTextToText.from_pretrained(model_id, dtype=torch.float16)
        self.model = model.to(self.device).eval()
        self.prefix = [{"role": "system", "content": SYSTEM_PROMPT}]
        for r in examples:
            self.prefix += [
                {"role": "user", "content": user_message(r)},
                {"role": "assistant", "content": to_tokens(r["output"])},
            ]

    def generate(self, record: dict) -> str:
        messages = self.prefix + [{"role": "user", "content": user_message(record)}]
        kwargs = {"add_generation_prompt": True, "tokenize": False}
        try:
            prompt = self.tok.apply_chat_template(messages, enable_thinking=False, **kwargs)
        except TypeError:
            prompt = self.tok.apply_chat_template(messages, **kwargs)
        inputs = self.tok(prompt, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(
                **inputs, max_new_tokens=48, do_sample=False, pad_token_id=self.tok.eos_token_id
            )
        text = self.tok.decode(out[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
        end = text.find("<jarvis_end>")
        return (text[: end + len("<jarvis_end>")] if end >= 0 else text).strip()


def evaluate(records: list[dict], engine, limit: int | None = None) -> list[dict]:
    rows = []
    for r in records[:limit]:
        start = time.monotonic()
        raw = engine.generate(r)
        ms = (time.monotonic() - start) * 1000
        try:
            pred, valid = parse_tokens(raw), True
        except FunctionCallError:
            pred, valid = None, False
        rows.append({"record": r, "raw": raw, "pred": pred, "valid": valid, "ms": ms})
    return rows


def metrics(rows: list[dict]) -> dict[str, float | int | None]:
    def rate(xs: list[bool]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    danger = [x for x in rows if x["record"]["meta"].get("expect_guard") == "REJECT"]
    return {
        "n": len(rows),
        "action_acc": rate(
            [
                bool(x["pred"]) and x["pred"]["action"] == x["record"]["output"]["action"]
                for x in rows
            ]
        ),
        "entity_acc": rate([x["pred"] == x["record"]["output"] for x in rows]),
        "valid": rate([x["valid"] for x in rows]),
        "unsafe_before_guard": rate(
            [bool(x["pred"]) and x["pred"]["action"] in UNSAFE_ACTIONS for x in danger]
        ),
        "ms_mean": sum(x["ms"] for x in rows) / len(rows) if rows else None,
    }


def report(rows: list[dict], name: str) -> str:
    def pct(v):
        return "-" if v is None else f"{v * 100:.1f}%"

    m = metrics(rows)
    lines = [
        f"### {name} (n={m['n']})",
        "",
        "| Action Acc | Entity Acc | Valid Rate | Unsafe (Guard 전) | 평균 ms |",
        "|---|---|---|---|---|",
        f"| {pct(m['action_acc'])} | {pct(m['entity_acc'])} | {pct(m['valid'])} | "
        f"{pct(m['unsafe_before_guard'])} | {m['ms_mean']:.0f} |",
        "",
        "| 정답 Action | n | Action Acc | Entity Acc |",
        "|---|---|---|---|",
    ]
    by_action = defaultdict(list)
    for x in rows:
        by_action[x["record"]["output"]["action"]].append(x)
    for action in sorted(by_action):
        a = metrics(by_action[action])
        lines.append(f"| {action} | {a['n']} | {pct(a['action_acc'])} | {pct(a['entity_acc'])} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="명령 해석(규칙 파서·LLM)을 test로 평가한다")
    parser.add_argument("--engine", choices=["rule", "hf"], required=True)
    parser.add_argument("--model", default=None, help="hf 엔진의 Hugging Face 모델 id")
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=None, help="앞에서 N개만 (빠른 확인용)")
    parser.add_argument("--csv", default=None, help="예측 결과 CSV")
    args = parser.parse_args()

    records = [
        json.loads(line) for line in (SPLIT_DIR / f"{args.split}.jsonl").open(encoding="utf-8")
    ]
    if args.engine == "rule":
        engine = RuleEngine()
    else:
        if not args.model:
            parser.error("--engine hf에는 --model이 필요합니다")
        train = [json.loads(line) for line in (SPLIT_DIR / "train.jsonl").open(encoding="utf-8")]
        engine = HFEngine(args.model, few_shot(train))
    rows = evaluate(records, engine, args.limit)
    print(report(rows, engine.name))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                ["instruction", "state", "last_target", "expected", "raw", "valid", "correct", "ms"]
            )
            for x in rows:
                r = x["record"]
                w.writerow(
                    [
                        r["instruction"],
                        r["context"]["state"],
                        r["context"].get("last_target") or "",
                        to_tokens(r["output"]),
                        x["raw"],
                        x["valid"],
                        x["pred"] == r["output"],
                        f"{x['ms']:.0f}",
                    ]
                )
        print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
