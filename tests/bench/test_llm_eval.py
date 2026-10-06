import json

from bench import llm_eval as le
from common.function_call import ACTIONS, DEVICES, parse_tokens, to_tokens

SPLIT = le.SPLIT_DIR


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (SPLIT / f"{name}.jsonl").open(encoding="utf-8")]


def rec(instruction: str, output: dict, expect_guard=None, state="COOKING") -> dict:
    return {
        "instruction": instruction,
        "context": {"state": state, "last_target": None},
        "output": output,
        "meta": {"expect_guard": expect_guard, "source": "seed"},
    }


class FixedEngine:
    """정해 둔 출력을 차례로 낸다."""

    name = "fixed"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)

    def generate(self, record: dict) -> str:
        return self.outputs.pop(0)


def test_metrics_counts_invalid_as_wrong_and_unsafe() -> None:
    records = [
        rec("후드 켜줘", {"action": "TURN_ON", "target": "hood"}),
        rec(
            "2번 화구 세게",
            {"action": "SET_LEVEL", "target": "burner_2", "level": 3},
            "REJECT",
            "DANGER",
        ),
        rec("2번 화구 켜", {"action": "TURN_ON", "target": "burner_2"}, "REJECT", "DANGER"),
    ]
    engine = FixedEngine([
        "<jarvis_1>(target=hood)<jarvis_end>",  # 정답
        "<jarvis_3>(target=burner_2, level=3)<jarvis_end>",  # 정답 + 위험 명령 (Guard 전)
        "켜 드릴게요",  # 형식 오류 → 오답, unsafe 아님
    ])  # fmt: skip
    m = le.metrics(le.evaluate(records, engine))
    assert m["valid"] == 2 / 3
    assert m["action_acc"] == 2 / 3 and m["entity_acc"] == 2 / 3
    assert m["unsafe_before_guard"] == 1 / 2


def test_rule_engine_on_committed_test_is_valid() -> None:
    rows = le.evaluate(load("test")[:50], le.RuleEngine())
    assert all(x["valid"] for x in rows)  # 규칙 파서는 항상 스키마에 맞는 출력


def test_few_shot_comes_only_from_train_and_covers_actions() -> None:
    train = load("train")
    examples = le.few_shot(train)
    keys = {(r["instruction"], json.dumps(r["context"])) for r in train}
    assert all((r["instruction"], json.dumps(r["context"])) in keys for r in examples)
    actions = {r["output"]["action"] for r in examples}
    assert actions == set(ACTIONS)  # 함수 14개가 예시에 한 번씩은 나온다
    test_texts = {r["instruction"] for r in load("test")}
    assert not [r for r in examples if r["instruction"] in test_texts]


def test_user_message_includes_context() -> None:
    r = rec("그거 꺼줘", {"action": "TURN_OFF", "target": "hood"})
    r["context"]["last_target"] = "hood"
    assert "마지막 장치=hood" in le.user_message(r) and "그거 꺼줘" in le.user_message(r)
    assert to_tokens(r["output"]) == "<jarvis_2>(target=hood)<jarvis_end>"


def test_system_prompt_lists_every_device_and_function() -> None:
    for device in DEVICES:
        assert device in le.SYSTEM_PROMPT
    for number in range(1, len(ACTIONS) + 1):
        assert f"\n{number} " in le.SYSTEM_PROMPT
    assert parse_tokens("<jarvis_12>()<jarvis_end>") == {"action": "REQUEST_PAYMENT"}
