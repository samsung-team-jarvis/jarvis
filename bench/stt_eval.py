"""STT 평가 (STT-06): 매니페스트 → CER · RTF · 호출어 인식 · STT→Action 정확도.

python -m bench.stt_eval data/stt/manifest.csv [--split test] [--csv out.csv]

매니페스트 (recipes/stt-eval.md §3):
  utt_id,speaker_id,noise_type,mic,path,transcript,action_label,split
  - path: --root(기본 data/) 기준 wav 경로
  - transcript: 정답 문장 (호출어 포함, 숫자는 ITN 결과처럼 아라비아 숫자로: "3분")
  - action_label: 정답 명령의 함수 토큰 (interfaces §3, 예: <jarvis_1>(target=hood)<jarvis_end>).
    호출어가 없는 발화(명령이 아니어야 함)는 비운다.

지표 정의:
  - CER: 띄어쓰기·문장부호를 지운 글자 기준 (jiwer.cer, 묶음 전체 합산)
  - RTF: 인식 시간 합 / 음성 길이 합
  - 호출어: 정답에 호출어가 있는 발화 중 받아쓴 문장에서도 호출로 판정된 비율, 오호출 = 반대
  - STT→Action: 받아쓴 문장 → 호출어 판정 → 규칙 파서 결과가 정답 명령과 같은 비율
    (전체 일치 / action만)
  - 정답 문장→파서: 정답 문장을 그대로 파서에 넣었을 때 (STT 오류를 뺀 파서 자체 정확도)
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import pathlib
import re
import sys
from collections import defaultdict
from typing import Protocol

import jiwer

from common.function_call import parse_tokens
from services.audio_svc.stt import Transcript
from services.audio_svc.wake import is_wake
from services.llm_svc.interpret import interpret

FIELDS = [
    "utt_id",
    "speaker_id",
    "noise_type",
    "mic",
    "path",
    "transcript",
    "action_label",
    "split",
]
GROUPS = [("전체", None), ("소음", "noise_type"), ("마이크", "mic"), ("화자", "speaker_id")]
_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")


class Engine(Protocol):
    def transcribe_file(self, path: str | pathlib.Path) -> Transcript: ...


def normalize(text: str) -> str:
    """CER 비교용: 띄어쓰기·문장부호 제거."""
    return _NOT_WORD.sub("", text)


def command_of(text: str) -> dict | None:
    """문장 → llm_svc와 같은 해석(호출어 → 오인식 사전 → 규칙 파서). 호출어가 없으면 None."""
    return interpret(text)


@dataclasses.dataclass
class Row:
    item: dict[str, str]
    hypothesis: str
    audio_ms: int
    stt_ms: int

    @property
    def expected(self) -> dict | None:
        label = self.item["action_label"].strip()
        return parse_tokens(label) if label else None

    @property
    def predicted(self) -> dict | None:
        return command_of(self.hypothesis)

    @property
    def from_reference(self) -> dict | None:
        return command_of(self.item["transcript"])


def load_manifest(path: pathlib.Path, split: str | None) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if missing := set(FIELDS) - set(reader.fieldnames or []):
            raise ValueError(f"매니페스트에 열이 없음: {sorted(missing)}")
        items = [row for row in reader if split is None or row["split"] == split]
    for item in items:
        if item["action_label"].strip():
            parse_tokens(item["action_label"].strip())  # 정답 명령 형식 오류는 먼저 알린다
    return items


def evaluate(items: list[dict[str, str]], engine: Engine, root: pathlib.Path) -> list[Row]:
    rows = []
    for item in items:
        result = engine.transcribe_file(root / item["path"])
        rows.append(Row(item, result.text, result.audio_ms, result.stt_ms))
    return rows


def metrics(rows: list[Row]) -> dict[str, float | int | None]:
    """한 묶음의 지표. 해당 발화가 없으면 None."""

    def rate(hits: list[bool]) -> float | None:
        return sum(hits) / len(hits) if hits else None

    refs = [normalize(r.item["transcript"]) for r in rows]
    hyps = [normalize(r.hypothesis) for r in rows]
    audio = sum(r.audio_ms for r in rows)
    wake_rows = [r for r in rows if is_wake(r.item["transcript"])]
    other_rows = [r for r in rows if not is_wake(r.item["transcript"])]
    labeled = [r for r in rows if r.expected is not None]
    return {
        "n": len(rows),
        "cer": jiwer.cer(refs, hyps) if rows else None,
        "rtf": sum(r.stt_ms for r in rows) / audio if audio else None,
        "wake_recall": rate([is_wake(r.hypothesis) for r in wake_rows]),
        "false_wake": rate([is_wake(r.hypothesis) for r in other_rows]),
        "action_exact": rate([r.predicted == r.expected for r in labeled]),
        "action_only": rate(
            [(r.predicted or {}).get("action") == r.expected["action"] for r in labeled]
        ),
        "parser_on_reference": rate([r.from_reference == r.expected for r in labeled]),
    }


COLUMNS = [
    ("n", "n"),
    ("cer", "CER"),
    ("rtf", "RTF"),
    ("wake_recall", "호출어 인식"),
    ("false_wake", "오호출"),
    ("action_exact", "STT→Action (전체)"),
    ("action_only", "STT→Action (action만)"),
    ("parser_on_reference", "정답 문장→파서"),
]


def _cell(key: str, v: float | int | None) -> str:
    if v is None:
        return "-"
    if key == "n":
        return str(v)
    if key == "rtf":
        return f"{v:.3f}"
    return f"{v * 100:.1f}%"


def report(rows: list[Row]) -> str:
    lines = []
    for title, field in GROUPS:
        groups: dict[str, list[Row]] = defaultdict(list)
        for r in rows:
            groups["전체" if field is None else r.item[field]].append(r)
        if field is not None and len(groups) < 2:
            continue  # 값이 하나뿐인 구분은 전체와 같다
        lines.append(f"\n### {title}\n")
        lines.append(f"| {title} | " + " | ".join(name for _, name in COLUMNS) + " |")
        lines.append("|---" * (len(COLUMNS) + 1) + "|")
        for key in sorted(groups):
            m = metrics(groups[key])
            lines.append(f"| {key} | " + " | ".join(_cell(k, m[k]) for k, _ in COLUMNS) + " |")
    return "\n".join(lines)


def write_csv(rows: list[Row], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([*FIELDS, "hypothesis", "cer", "audio_ms", "stt_ms", "predicted", "correct"])
        for r in rows:
            cer = jiwer.cer(normalize(r.item["transcript"]), normalize(r.hypothesis))
            correct = "" if r.expected is None else r.predicted == r.expected
            w.writerow([*(r.item[k] for k in FIELDS), r.hypothesis, f"{cer:.4f}", r.audio_ms,
                        r.stt_ms, r.predicted, correct])  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser(description="STT 매니페스트로 CER·RTF·STT→Action을 잰다")
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("data"))
    parser.add_argument("--split", default=None, help="이 split만 (예: test)")
    parser.add_argument("--csv", default=None, help="발화별 결과 CSV")
    parser.add_argument("--engine", default="sensevoice", choices=["sensevoice"])
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--language", default="ko")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    try:
        items = load_manifest(args.manifest, args.split)
    except (OSError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    if not items:
        print("평가할 발화가 없습니다 (--split 확인).", file=sys.stderr)
        return 1

    from services.audio_svc.stt import SenseVoice, model_dir_from_env

    engine = SenseVoice(
        args.model_dir or model_dir_from_env(), language=args.language, num_threads=args.threads
    )
    rows = evaluate(items, engine, args.root)
    print(f"## STT 평가 — {args.manifest} (split={args.split or '전체'}, engine={args.engine})")
    print(report(rows))
    if args.csv:
        write_csv(rows, args.csv)
        print(f"\nCSV: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
