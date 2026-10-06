import csv
import pathlib

import pytest

from bench import llm_errors as le
from common.function_call import to_tokens

HOOD_ON = {"action": "TURN_ON", "target": "hood"}
ASK_TARGET = {"action": "ASK_CLARIFY", "for_action": "TURN_ON", "missing": ["target"]}


@pytest.mark.parametrize(
    ("expected", "raw", "kind"),
    [
        (HOOD_ON, "<jarvis_1>(target=hood)<jarvis_end>", None),
        (HOOD_ON, "후드를 켤게요", "format"),
        (HOOD_ON, "<jarvis_1>(target=alarm)<jarvis_end>", "invented"),  # 없는 장치
        (HOOD_ON, "<jarvis_3>(target=hood)<jarvis_end>", "invented"),  # 세기 인자 빠짐
        (ASK_TARGET, "<jarvis_1>(target=hood)<jarvis_end>", "filled_missing"),
        (HOOD_ON, "<jarvis_1>(target=?)<jarvis_end>", "needless_ask"),
        ({"action": "UNSUPPORTED"}, "<jarvis_13>()<jarvis_end>", "unsupported_executed"),
        (HOOD_ON, "<jarvis_10>()<jarvis_end>", "refused"),
        ({"action": "CANCEL_TIMER"}, "<jarvis_8>()<jarvis_end>", "wrong_action"),
        (ASK_TARGET, "<jarvis_9>()<jarvis_end>", "wrong_action"),  # 하려던 함수가 다름
        (HOOD_ON, "<jarvis_1>(target=fan)<jarvis_end>", "wrong_target"),
        (
            {"action": "SET_LEVEL", "target": "hood", "level": 3},
            "<jarvis_3>(target=hood, level=1)<jarvis_end>",
            "wrong_value",
        ),
    ],
)
def test_classify(expected: dict, raw: str, kind: str | None) -> None:
    assert le.classify(expected, raw) == kind


def test_flags() -> None:
    off = {"action": "TURN_OFF", "target": "fan"}
    assert le.flags(off, "<jarvis_8>()<jarvis_end>", "not_urgent") == {
        "emergency",
        "wrong_execution",
    }
    unsupported = {"action": "UNSUPPORTED"}
    assert le.flags(unsupported, "<jarvis_12>()<jarvis_end>", "") == {"wrong_execution"}
    assert le.flags(off, "<jarvis_2>(target=hood)<jarvis_end>", "pronoun") == {
        "pronoun",
        "wrong_execution",
    }
    assert le.flags(off, to_tokens(off), "pronoun") == set()  # 맞으면 표시 없음


def test_every_error_has_exactly_one_type(tmp_path: pathlib.Path) -> None:
    rows = [
        ("후드 켜줘", HOOD_ON, "<jarvis_1>(target=hood)<jarvis_end>"),
        ("후드 켜줘", HOOD_ON, "<jarvis_10>()<jarvis_end>"),
        ("불 켜줘", ASK_TARGET, "<jarvis_1>(target=burner_1)<jarvis_end>"),
        ("고마워", {"action": "UNSUPPORTED"}, "네"),
    ]
    path = tmp_path / "pred.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["instruction", "expected", "raw", "group", "category"])
        w.writeheader()
        for text, expected, raw in rows:
            w.writerow({"instruction": text, "expected": to_tokens(expected), "raw": raw,
                        "group": "g", "category": ""})  # fmt: skip
    result = le.analyze(le.load(path))
    assert result["n"] == 4 and result["errors"] == 3 == sum(result["types"].values())
    assert result["families"]["g"] == 3
    text = le.report({"pred": result})
    assert "**3 / 4**" in text and "지원 외로 거절 | 1" in text
