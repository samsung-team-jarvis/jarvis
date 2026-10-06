import pytest

from common.function_call import to_tokens
from services.llm_svc import prompt
from training.llm import train_lora as tl


class FakeTokenizer:
    """글자 하나 = 토큰 하나. chat template은 역할 표시만 붙인다."""

    eos_token = "§"

    def apply_chat_template(self, messages, add_generation_prompt, tokenize, enable_thinking):
        assert add_generation_prompt and not tokenize and enable_thinking is False
        body = "".join(f"[{m['role']}]{m['content']}" for m in messages)
        return body + "[assistant]"

    def __call__(self, text, add_special_tokens=True):
        return {"input_ids": [ord(ch) for ch in text]}


RECORD = {
    "instruction": "후드 켜줘",
    "context": {"state": "COOKING", "last_target": None},
    "output": {"action": "TURN_ON", "target": "hood"},
}


def test_prompt_uses_the_short_system_prompt_and_user_message() -> None:
    text = tl.render_prompt(FakeTokenizer(), RECORD)
    assert f"[system]{prompt.FINETUNED_SYSTEM_PROMPT}" in text
    assert "[user]상황: state=COOKING, 마지막 장치=없음\n말: 후드 켜줘" in text
    assert text.endswith("[assistant]")


def test_loss_only_on_answer_and_end_token() -> None:
    tok = FakeTokenizer()
    ids, labels = tl.encode(tok, RECORD)
    answer = to_tokens(RECORD["output"]) + tok.eos_token
    n_prompt = len(tl.render_prompt(tok, RECORD))
    assert len(ids) == len(labels) == n_prompt + len(answer)
    assert labels[:n_prompt] == [-100] * n_prompt  # 지시문·사용자 메시지는 맞히게 하지 않는다
    assert "".join(map(chr, labels[n_prompt:])) == answer
    assert ids[n_prompt:] == labels[n_prompt:]


def test_learning_rate_warms_up_then_decays_to_zero() -> None:
    f = tl.lr_lambda(warmup=4, total=20)
    assert [f(s) for s in range(4)] == pytest.approx([0.25, 0.5, 0.75, 1.0])
    assert f(4) == pytest.approx(1.0)
    assert f(12) == pytest.approx(0.5)
    assert f(20) == pytest.approx(0.0)
    assert all(f(s) >= f(s + 1) for s in range(4, 20))


def test_user_message_marks_missing_last_target() -> None:
    ctx = {"state": "IDLE", "last_target": "burner_1"}
    assert (
        prompt.user_message("그거 꺼줘", ctx)
        == "상황: state=IDLE, 마지막 장치=burner_1\n말: 그거 꺼줘"
    )
    assert "마지막 장치=없음" in prompt.user_message("후드 켜줘", {"state": "IDLE"})
