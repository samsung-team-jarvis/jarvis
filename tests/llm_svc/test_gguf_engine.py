"""llama.cpp 생성기 (LLM-18): 학습과 같은 입력 문자열, <jarvis_end>까지만 쓴다."""

import pytest

from services.llm_svc import prompt
from services.llm_svc.gguf_engine import GGUFGenerator

# 학습 기록(runs/llm/<v4>/train_log.json)의 prompt_example — tokenizer가 만든 문자열
TRAIN_PROMPT_EXAMPLE = (
    "<|im_start|>system\n가게 음성 명령을 함수 토큰 한 줄로 바꾼다.<|im_end|>\n"
    "<|im_start|>user\n상황: state=COOKING, 마지막 장치=없음\n말: 일번 화구 켜줘<|im_end|>\n"
    "<|im_start|>assistant\n<think>\n\n</think>\n\n"
)
CTX = {"state": "COOKING", "last_target": None}


def test_chat_prompt_matches_the_training_input() -> None:
    assert prompt.chat_prompt("일번 화구 켜줘", CTX) == TRAIN_PROMPT_EXAMPLE


def test_chat_prompt_matches_the_tokenizer_template_when_available() -> None:
    transformers = pytest.importorskip("transformers")
    try:
        tok = transformers.AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B", local_files_only=True)
    except OSError:
        pytest.skip("Qwen3-0.6B tokenizer가 이 PC에 없음")
    ctx = {"state": "DANGER", "last_target": "fryer"}
    messages = [
        {"role": "system", "content": prompt.FINETUNED_SYSTEM_PROMPT},
        {"role": "user", "content": prompt.user_message("그거 꺼", ctx)},
    ]
    expected = tok.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False, enable_thinking=False
    )
    assert prompt.chat_prompt("그거 꺼", ctx) == expected


class FakeLlama:
    def __init__(self, text: str, n: int) -> None:
        self.text, self.n, self.prompt_ids = text, n, None

    def tokenize(self, data: bytes, add_bos: bool, special: bool) -> list[int]:
        assert not add_bos and special  # chat template의 특수 토큰을 글자가 아니라 토큰으로
        return list(data)

    def create_completion(self, ids, max_tokens, temperature, top_k):
        self.prompt_ids = ids
        assert (max_tokens, temperature, top_k) == (48, 0.0, 1)  # greedy, HF와 같은 길이
        return {"choices": [{"text": self.text}], "usage": {"completion_tokens": self.n}}


def generator(text: str, n: int) -> GGUFGenerator:
    g = GGUFGenerator.__new__(GGUFGenerator)  # llama_cpp 없이
    g.llm = FakeLlama(text, n)
    return g


def test_output_is_cut_at_the_end_token() -> None:
    g = generator("<jarvis_1>(target=hood)<jarvis_end> 설명이 더 붙음", 20)
    assert g("후드 켜", CTX) == ("<jarvis_1>(target=hood)<jarvis_end>", 20)
    assert bytes(g.llm.prompt_ids).decode() == prompt.chat_prompt("후드 켜", CTX)


def test_output_without_end_token_is_returned_as_is() -> None:
    g = generator(" <jarvis_1>(target=hood", 48)
    assert g("후드 켜", CTX) == ("<jarvis_1>(target=hood", 48)  # 검증에서 실패 → 규칙 파서
