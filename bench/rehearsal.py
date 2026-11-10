"""시연 리허설 (DOC-09): 대본 → 합성 음성 wav, 녹화 → 기대 판정과 맞춰 보기.

python -m bench.rehearsal make     # bench/rehearsal/demo.yaml → data/stt/rehearsal/demo.wav (macOS)
python3 scripts/launch.py --config scripts/launch_demo.yaml \\
    --arg audio_svc="--input data/stt/rehearsal/demo.wav --realtime --session rehearsal"
    # 마지막 응답이 나온 뒤 Ctrl+C
python -m bench.rehearsal check data/sessions/rehearsal.jsonl

확인은 Safety Guard의 판정(`guard/decision`)을 대본의 기대와 **차례대로** 맞춘다. 기대에 적은 필드
(action·target·level 등)와 decision만 비교하고, 기대 사이에 다른 판정이 끼어 있어도 된다
(예: 긴급 정지 뒤 명령 해석이 낸 같은 긴급 정지는 Guard가 무시한다). 받아쓴 문장도 함께 보여 준다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import wave
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bench/rehearsal/demo.yaml"
OUT = ROOT / "data/stt/rehearsal/demo.wav"
RATE = 16000
LEAD_S = 3.0  # 서비스가 첫 문장을 받을 준비 시간


def load_script(path: pathlib.Path) -> dict[str, Any]:
    script = yaml.safe_load(path.read_text(encoding="utf-8"))
    for step in script["steps"]:
        if "decision" not in step["expect"] or "action" not in step["expect"]:
            raise ValueError(f"expect에는 action과 decision이 있어야 합니다: {step}")
    return script


def make_wav(script: dict[str, Any], out: pathlib.Path) -> float:
    """macOS `say`로 문장마다 합성 → 16 kHz mono 16-bit로 바꿔 사이에 무음을 넣고 잇는다."""
    out.parent.mkdir(parents=True, exist_ok=True)
    gap = b"\x00\x00" * int(RATE * script.get("gap_s", 6.0))
    with tempfile.TemporaryDirectory() as tmp, wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"\x00\x00" * int(RATE * LEAD_S))
        for i, step in enumerate(script["steps"]):
            aiff, part = pathlib.Path(tmp) / f"{i}.aiff", pathlib.Path(tmp) / f"{i}.wav"
            subprocess.run(
                ["say", "-v", script.get("voice", "Yuna"), "-o", aiff, step["say"]], check=True
            )
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", f"LEI16@{RATE}", "-c", "1", aiff, part],
                check=True,
            )
            with wave.open(str(part)) as p:
                w.writeframes(p.readframes(p.getnframes()))
            w.writeframes(gap)
        return w.getnframes() / RATE


def matches(expect: dict[str, Any], decision: dict[str, Any]) -> bool:
    if decision["decision"] != expect["decision"]:
        return False
    call = decision["call"]
    return all(call.get(k) == v for k, v in expect.items() if k != "decision")


def check(script: dict[str, Any], messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """기대 판정을 녹화 속 guard/decision과 차례대로 맞춘다 → 단계별 결과."""
    decisions = [m["payload"] for m in messages if m["type"] == "guard/decision"]
    results, i = [], 0
    for step in script["steps"]:
        found = next(
            (j for j in range(i, len(decisions)) if matches(step["expect"], decisions[j])), None
        )
        results.append(
            {
                "say": step["say"],
                "expect": step["expect"],
                "got": decisions[found] if found is not None else None,
            }
        )
        if found is not None:
            i = found + 1
    return results


def describe(d: dict[str, Any]) -> str:
    args = ", ".join(f"{k}={v}" for k, v in d.items() if k not in ("action", "decision", "reason"))
    return f"{d['action']}({args}) {d['decision']}"


def report(results: list[dict[str, Any]], heard: list[str]) -> str:
    ok = sum(r["got"] is not None for r in results)
    lines = [
        f"### 시연 리허설: {ok} / {len(results)} 단계 통과",
        "",
        "| # | 대본 | 기대 판정 | 결과 |",
        "|---|---|---|---|",
    ]
    for n, r in enumerate(results, 1):
        lines.append(
            f"| {n} | {r['say']} | {describe(r['expect'])} | {'통과' if r['got'] else '**없음**'} |"
        )
    lines += ["", "받아쓴 문장 (차례대로): " + " / ".join(heard)]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="시연 대본으로 wav를 만들고 녹화를 확인한다")
    sub = parser.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="대본 → 합성 음성 wav (macOS say)")
    m.add_argument("--script", type=pathlib.Path, default=SCRIPT)
    m.add_argument("--out", type=pathlib.Path, default=OUT)
    c = sub.add_parser("check", help="녹화(jsonl) → 기대 판정과 맞춰 보기")
    c.add_argument("session", type=pathlib.Path)
    c.add_argument("--script", type=pathlib.Path, default=SCRIPT)
    args = parser.parse_args()

    script = load_script(args.script)
    if args.cmd == "make":
        seconds = make_wav(script, args.out)
        print(f"{args.out}: {len(script['steps'])}문장, {seconds:.1f}초")
        return 0
    messages = [json.loads(line) for line in args.session.open(encoding="utf-8")]
    heard = [m["payload"]["text"] for m in messages if m["type"] == "stt/text"]
    results = check(script, messages)
    print(report(results, heard))
    return 0 if all(r["got"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
