import csv
import pathlib

from bench import llm_fallback as lf
from bench.llm_eval import CSV_COLUMNS


def write(path: pathlib.Path, rows: list[tuple[str, str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for text, expected, raw in rows:
            w.writerow({"instruction": text, "state": "COOKING", "last_target": "",
                        "expected": expected, "raw": raw, "valid": "", "correct": "", "ms": "1",
                        "template_id": "t", "group": "g", "category": ""})  # fmt: skip


def test_invalid_llm_rows_are_replaced_by_rule_parser(tmp_path: pathlib.Path) -> None:
    hood_on = "<jarvis_1>(target=hood)<jarvis_end>"
    path = tmp_path / "pred.csv"
    write(path, [
        ("후드 켜줘", hood_on, hood_on),                                  # LLM 맞음
        ("후드 켜줘", hood_on, "<jarvis_1>(target=volume)<jarvis_end>"),  # 검증 실패 → 규칙 파서
        ("후드 켜줘", hood_on, "<jarvis_2>(target=hood)<jarvis_end>"),    # 통과했지만 틀림 → 그대로
    ])  # fmt: skip
    with path.open(encoding="utf-8", newline="") as f:
        rows = lf.apply(list(csv.DictReader(f)))
    assert [x["fallback"] for x in rows] == [False, True, False]
    assert [x["entity_ok"] for x in rows] == [True, True, False]
    assert "| 66.7% | 66.7% | 66.7% | 1 | 1 / 1 |" in lf.report(rows, "pred")
