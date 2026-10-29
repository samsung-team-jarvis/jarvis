"""llm_svc 실행 (규칙 파서만, 또는 LLM + 검증 실패 시 규칙 파서).

python -m services.llm_svc                               # 규칙 파서만, 버스는 JARVIS_BUS
python -m services.llm_svc --bus mqtt://localhost:1883
python -m services.llm_svc parse "후드 세게 틀어 줘"       # 버스 없이 결과만 보기
# LLM + 검증 실패 시 규칙 파서 (LLM-09). 실행용은 GGUF(llama.cpp CPU, LLM-18), HF 폴더는 Mac 비교용
.venv-llm/bin/python -m services.llm_svc --model runs/llm/llm_qwen3-0.6b_jarvis_v4-q8_0.gguf
.venv-llm/bin/python -m services.llm_svc --model runs/llm/llm_qwen3-0.6b_jarvis_v4 parse "후드 세게"
"""

from __future__ import annotations

import argparse
import datetime
import json
import signal
import sys
import threading

from common.bus import connect
from common.function_call import to_tokens
from common.messages import Envelope
from services.llm_svc.interpret import resolve
from services.llm_svc.service import DEFAULT_STATE, LlmService


def show(msg: Envelope) -> None:
    p = msg.payload
    how = "규칙 파서" if p["fallback"] else "LLM"
    if not p["valid"]:
        how = "LLM 검증 실패 → 규칙 파서"
    call = json.dumps(p["call"], ensure_ascii=False)
    print(f"[llm/function_call] {p['raw_text']!r} → {call} ({how}, {p['gen_ms']:.0f} ms)")


def main() -> int:
    parser = argparse.ArgumentParser(description="stt/text를 명령(Function Call)으로 바꿔 발행한다")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("parse", help="버스 없이 문장 하나를 파싱해 출력")
    p.add_argument("text")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="heartbeat session_id (생략 시 s_<시각>)")
    parser.add_argument("--quiet", action="store_true", help="발행할 때마다 출력하지 않음")
    parser.add_argument(
        "--model",
        default=None,
        help="학습한 LLM: .gguf 파일(llama.cpp CPU) 또는 HF 폴더 (.venv-llm). 생략 시 규칙 파서만",
    )
    args = parser.parse_args()

    generate = None
    if args.model and args.model.endswith(".gguf"):
        from services.llm_svc.gguf_engine import GGUFGenerator

        generate = GGUFGenerator(args.model)
    elif args.model:
        from services.llm_svc.hf_engine import HFGenerator

        generate = HFGenerator(args.model)

    if args.cmd == "parse":
        r = resolve(args.text, {"state": DEFAULT_STATE, "last_target": None}, generate)
        print(json.dumps(r.call, ensure_ascii=False))
        print(to_tokens(r.call))
        if generate:
            llm = "(검증 실패 → 규칙 파서)" if r.fallback else r.raw_text
            print(f"LLM 출력: {llm}")
        return 0

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="llm_svc")
    service = LlmService(bus, session_id, on_call=None if args.quiet else show, generate=generate)
    service.start()
    mode = f"LLM {args.model} + 규칙 파서 대체" if args.model else "규칙 파서"
    print(f"llm_svc({mode}) 시작: stt/text 구독 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.2):
            service.heartbeat()
    except KeyboardInterrupt:
        pass
    bus.close()
    print(
        f"OK: llm/function_call {service.published}건 발행 "
        f"(호출어 없어 무시 {service.ignored}건, LLM 검증 실패 대체 {service.fallbacks}건)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
