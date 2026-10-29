"""Mac(HF transformers)에서 학습한 LoRA 모델로 함수 토큰을 만든다 — 실행용은 GGUF(gguf_engine.py).

torch·transformers가 있는 환경(.venv-llm)에서만 쓴다. 입력은 학습·평가와 같다 (prompt.py,
bench/llm_eval.py `--finetuned`): 짧은 지시문 + 사용자 메시지, greedy, 최대 48토큰.
"""

from __future__ import annotations

from typing import Any

from services.llm_svc import prompt

END = "<jarvis_end>"


class HFGenerator:
    def __init__(self, model_dir: str, device: str | None = None) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float16)
        self.model = model.to(self.device).eval()

    def __call__(self, instruction: str, context: dict[str, Any]) -> tuple[str, int]:
        messages = [
            {"role": "system", "content": prompt.FINETUNED_SYSTEM_PROMPT},
            {"role": "user", "content": prompt.user_message(instruction, context)},
        ]
        text = self.tok.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False, enable_thinking=False
        )
        inputs = self.tok(text, return_tensors="pt").to(self.device)
        with self.torch.no_grad():
            out = self.model.generate(
                **inputs, max_new_tokens=48, do_sample=False, pad_token_id=self.tok.eos_token_id
            )
        new = out[0][inputs["input_ids"].shape[1] :]
        raw = self.tok.decode(new, skip_special_tokens=True)
        end = raw.find(END)
        return (raw[: end + len(END)] if end >= 0 else raw).strip(), len(new)
