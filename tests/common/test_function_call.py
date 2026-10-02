import json
import pathlib

import pytest

from common.function_call import ACTIONS, FunctionCallError, parse_tokens, to_tokens, validate

DOC = pathlib.Path(__file__).parents[2] / "docs/architecture/interfaces.md"


def doc_examples() -> list[tuple[str, dict]]:
    """interfaces.md §3.3 예시 표의 (함수 토큰, 버스 JSON). 문서와 코드가 어긋나면 깨진다."""
    text = DOC.read_text(encoding="utf-8")
    section = text.split("### 3.3 예시", 1)[1].split("###", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 3 and cells[1].startswith("`<jarvis_"):
            rows.append((cells[1].strip("`"), json.loads(cells[2].strip("`"))))
    return rows


EXAMPLES = doc_examples()


def test_doc_has_examples() -> None:
    assert len(EXAMPLES) >= 10


@pytest.mark.parametrize(("tokens", "call"), EXAMPLES)
def test_parse_tokens(tokens: str, call: dict) -> None:
    assert parse_tokens(tokens) == call


@pytest.mark.parametrize(("tokens", "call"), EXAMPLES)
def test_to_tokens_round_trip(tokens: str, call: dict) -> None:
    assert parse_tokens(to_tokens(call)) == call


def test_examples_cover_every_action() -> None:
    assert {c["action"] for _, c in EXAMPLES} == set(ACTIONS)


def test_parse_tolerates_spaces() -> None:
    assert parse_tokens("  <jarvis_3>( level=2 ,target=hood )<jarvis_end>\n") == {
        "action": "SET_LEVEL",
        "target": "hood",
        "level": 2,
    }


@pytest.mark.parametrize(
    ("tokens", "error"),
    [
        ("후드 켜", "형식"),
        ("<jarvis_1>(target=hood)", "형식"),  # 끝 토큰 없음 (생성이 잘림)
        ("<jarvis_11>()<jarvis_end>", "함수 번호"),
        ("<jarvis_1>(target=all)<jarvis_end>", "target"),  # 모두 켜기는 지원 안 함
        ("<jarvis_1>(target=fryer)<jarvis_end>", "target"),
        ("<jarvis_1>()<jarvis_end>", "필수"),
        ("<jarvis_3>(target=hood, level=5)<jarvis_end>", "level"),
        ("<jarvis_3>(target=hood, level=high)<jarvis_end>", "숫자"),
        ("<jarvis_4>(min=61)<jarvis_end>", "duration_s"),
        ("<jarvis_4>(sec=0)<jarvis_end>", "duration_s"),
        ("<jarvis_1>(min=3)<jarvis_end>", "없는 파라미터"),
        ("<jarvis_7>(target=?)<jarvis_end>", "없는 파라미터"),
        ("<jarvis_8>(target=hood)<jarvis_end>", "target"),
        ("<jarvis_2>(target=hood, target=all)<jarvis_end>", "인자"),
        ("<jarvis_2>(color=red)<jarvis_end>", "인자"),
        ("<jarvis_2>(target)<jarvis_end>", "인자"),
    ],
)
def test_parse_rejects_invalid(tokens: str, error: str) -> None:
    with pytest.raises(FunctionCallError, match=error):
        parse_tokens(tokens)


@pytest.mark.parametrize(
    "call",
    [
        {"action": "JUMP"},
        {"action": "SET_LEVEL", "target": "hood", "level": True},  # bool은 정수로 보지 않음
        {"action": "SET_LEVEL", "target": "hood", "level": 2, "need_confirmation": False},
        {"action": "SET_TIMER", "duration_s": 3.5},
        {"action": "ASK_CLARIFY", "for_action": "TURN_ON", "missing": []},
        {"action": "ASK_CLARIFY", "for_action": None, "missing": ["target"]},
        {"action": "ASK_CLARIFY", "for_action": "TURN_ON", "missing": ["color"]},
    ],
)
def test_validate_rejects(call: dict) -> None:
    with pytest.raises(FunctionCallError):
        validate(call)
