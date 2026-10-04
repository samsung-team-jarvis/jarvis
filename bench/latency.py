"""지연 분해 (INFRA-06): recorder 녹화에서 발화 한 건마다 구간별 지연(ms)을 계산한다.

python -m bench.latency data/sessions/<세션>.jsonl [...] [--csv out.csv]

같은 세션 안에서 메시지를 시간 순으로 이어 붙인다 (메시지에 상관관계 ID가 없어서).
  stt/text(wake) → llm/function_call → guard/decision → control/command ─seq─ control/result
그래서 다른 메시지를 받아 만든 메시지는 원래 session_id를 이어 써야 한다 (interfaces §1).
`mono`는 각 서비스가 발행할 때 찍은 time.monotonic()이고, 같은 기기의 단조 시계라 프로세스가
달라도 뺄 수 있다. 다른 기기(가상 주방 PC)의 시각은 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import math
import pathlib
import sys
from collections import defaultdict
from collections.abc import Iterable

from common.messages import Envelope
from services.recorder.store import read_session

# (이름, 설명) — 표·CSV의 열 순서
SEGMENTS = [
    ("vad_wait", "발화 끝 → STT 시작 (VAD가 발화 끝을 판단하는 대기 포함)"),
    ("stt", "STT 인식 (stt_ms)"),
    ("to_call", "stt/text 발행 → llm/function_call 발행 (전달 + 파서/LLM)"),
    ("to_guard", "llm/function_call → guard/decision"),
    ("to_command", "guard/decision → control/command"),
    ("to_ack", "control/command → control/result (가상 주방 왕복)"),
    ("e2e", "발화 끝 → 기록된 마지막 단계"),
]
STAGES = ["stt/text", "llm/function_call", "guard/decision", "control/command", "control/result"]


@dataclasses.dataclass
class Utterance:
    stt: Envelope
    call: Envelope | None = None
    decision: Envelope | None = None
    command: Envelope | None = None
    result: Envelope | None = None

    @property
    def speech_end(self) -> float:
        return self.stt.payload["speech_end_mono"]

    def last_stage(self) -> str:
        chain = [self.stt, self.call, self.decision, self.command, self.result]
        reached = [stage for stage, msg in zip(STAGES, chain, strict=True) if msg is not None]
        return reached[-1]

    def segments(self) -> dict[str, float | None]:
        """구간별 ms. 녹화에 없는 단계의 구간은 None."""

        def gap(a: Envelope | None, b: Envelope | None) -> float | None:
            return (b.mono - a.mono) * 1000 if a and b else None

        stt_ms = float(self.stt.payload["stt_ms"])
        to_stt = (self.stt.mono - self.speech_end) * 1000
        last = self.result or self.command or self.decision or self.call or self.stt
        return {
            "vad_wait": to_stt - stt_ms,
            "stt": stt_ms,
            "to_call": gap(self.stt, self.call),
            "to_guard": gap(self.call, self.decision),
            "to_command": gap(self.decision, self.command),
            "to_ack": gap(self.command, self.result),
            "e2e": (last.mono - self.speech_end) * 1000,
        }


def link(messages: Iterable[Envelope]) -> list[Utterance]:
    """메시지를 세션별·시간 순으로 이어 발화 목록을 만든다. 호출어가 없는 발화는 뺀다."""
    by_session: dict[str, list[Envelope]] = defaultdict(list)
    for msg in messages:
        by_session[msg.session_id].append(msg)

    utterances: list[Utterance] = []
    for msgs in by_session.values():
        session: list[Utterance] = []
        for msg in sorted(msgs, key=lambda m: m.mono):
            if msg.type == "stt/text":
                if msg.payload["wake"]:
                    session.append(Utterance(stt=msg))
            elif msg.type == "llm/function_call":
                _attach(session, msg, "call", after="stt")
            elif msg.type == "guard/decision":
                _attach(session, msg, "decision", after="call")
            elif msg.type == "control/command":
                _attach(session, msg, "command", after="decision")
            elif msg.type == "control/result":
                for u in reversed(session):
                    if (
                        u.command
                        and u.result is None
                        and u.command.payload["seq"] == msg.payload["seq"]
                    ):
                        u.result = msg
                        break
        utterances.extend(session)
    return sorted(utterances, key=lambda u: u.stt.mono)


def _attach(session: list[Utterance], msg: Envelope, field: str, after: str) -> None:
    """가장 최근 발화 중 앞 단계는 있고 이 단계는 아직 없는 것에 붙인다."""
    for u in reversed(session):
        if getattr(u, after) is not None and getattr(u, field) is None:
            setattr(u, field, msg)
            return


def percentile(values: list[float], p: float) -> float:
    """nearest-rank 백분위수 (표본이 적어도 실제 측정값 중 하나를 고른다)."""
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize(utterances: list[Utterance]) -> dict[str, dict[str, float]]:
    """구간별 n·평균·p50·p95·최대 (값이 있는 발화만)."""
    out = {}
    for name, _ in SEGMENTS:
        values = [v for u in utterances if (v := u.segments()[name]) is not None]
        if values:
            out[name] = {
                "n": len(values),
                "mean": sum(values) / len(values),
                "p50": percentile(values, 50),
                "p95": percentile(values, 95),
                "max": max(values),
            }
    return out


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.0f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="recorder 녹화에서 발화별 구간 지연(ms)을 계산한다"
    )
    parser.add_argument("files", nargs="+", help="data/sessions/*.jsonl")
    parser.add_argument("--csv", default=None, help="발화별 결과를 CSV로 저장")
    args = parser.parse_args()

    messages = [m for f in args.files for m in read_session(pathlib.Path(f))]
    utterances = link(messages)
    if not utterances:
        print("호출어가 있는 stt/text가 없습니다.", file=sys.stderr)
        return 1

    names = [n for n, _ in SEGMENTS]
    print("| 세션 | 발화 | " + " | ".join(names) + " | 마지막 단계 |")
    print("|---" * (len(names) + 3) + "|")
    for u in utterances:
        seg = u.segments()
        cells = " | ".join(_fmt(seg[n]) for n in names)
        print(f"| {u.stt.session_id} | {u.stt.payload['text']} | {cells} | {u.last_stage()} |")

    print("\n| 구간 | n | 평균 | p50 | p95 | 최대 | 의미 |")
    print("|---|---|---|---|---|---|---|")
    for name, desc in SEGMENTS:
        s = summarize(utterances).get(name)
        if s:
            print(
                f"| {name} | {s['n']} | {s['mean']:.0f} | {s['p50']:.0f} | {s['p95']:.0f} "
                f"| {s['max']:.0f} | {desc} |"
            )
        else:
            print(f"| {name} | 0 | - | - | - | - | {desc} (녹화에 없음) |")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["session_id", "text", *names, "last_stage"])
            for u in utterances:
                seg = u.segments()
                w.writerow([u.stt.session_id, u.stt.payload["text"], *[seg[n] for n in names],
                            u.last_stage()])  # fmt: skip
        print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
