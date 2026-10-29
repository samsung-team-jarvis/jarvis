"""llama.cpp(GGUF, CPU)로 학습한 LoRA 모델을 돌려 함수 토큰을 만든다 (LLM-18).

결정: docs/decisions/2026-10-29-llamacpp-and-rebalance.md — RKLLM(NPU) 대신 CPU.
보드에서도 같은 파일을 쓴다.
llama-cpp-python이 있는 환경(.venv-llm)에서만 쓴다. 입력은 학습과 같은 문자열(prompt.chat_prompt),
greedy, 최대 48토큰, 모델이 대화 끝 토큰을 내면 멈춘다 — HFGenerator와 같은 조건.
"""

from __future__ import annotations

from typing import Any

from services.llm_svc import prompt

END = "<jarvis_end>"
N_CTX = 256  # 입력 최장 ~105토큰 + 출력 48 (학습 문장 기준)
N_THREADS = 4  # 보드(RK3588) 큰 코어 수에 맞춘 기본값


class GGUFGenerator:
    def __init__(self, model_path: str, n_threads: int = N_THREADS, gpu: bool = False) -> None:
        from llama_cpp import Llama

        self.llm = Llama(
            model_path=model_path,
            n_ctx=N_CTX,
            n_threads=n_threads,
            # 입력 처리 스레드 기본값은 코어 전부(저전력 코어 포함)라 오히려 느리고 들쭉날쭉하다
            # (Mac 10코어: 평균 691 → 225 ms, 최대 2,485 → 296 ms, #124)
            n_threads_batch=n_threads,
            n_gpu_layers=-1 if gpu else 0,
            verbose=False,
        )

    def __call__(self, instruction: str, context: dict[str, Any]) -> tuple[str, int]:
        text = prompt.chat_prompt(instruction, context)
        ids = self.llm.tokenize(text.encode("utf-8"), add_bos=False, special=True)
        out = self.llm.create_completion(ids, max_tokens=48, temperature=0.0, top_k=1)
        raw = out["choices"][0]["text"]
        end = raw.find(END)
        tokens = out["usage"]["completion_tokens"]
        return (raw[: end + len(END)] if end >= 0 else raw).strip(), tokens
