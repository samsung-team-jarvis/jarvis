"""CPU 코어 고정 (LLM-19)."""

import os

import pytest

from common.cpus import parse_cpus, pin


def test_parse_ranges_and_lists() -> None:
    assert parse_cpus("4-7") == {4, 5, 6, 7}
    assert parse_cpus("4,5, 6,7") == {4, 5, 6, 7}
    assert parse_cpus("0,4-5") == {0, 4, 5}


@pytest.mark.parametrize("bad", ["", "a-b", "7-4", "4-", "big"])
def test_bad_formats_are_rejected(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_cpus(bad)


def test_no_option_does_nothing() -> None:
    assert pin(None) is None and pin("") is None


def test_pin_sets_affinity_on_linux(monkeypatch) -> None:
    applied = {}
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: set(range(8)), raising=False)
    monkeypatch.setattr(
        os, "sched_setaffinity", lambda pid, cpus: applied.update(pid=pid, cpus=cpus), raising=False
    )
    assert pin("4-7") == {4, 5, 6, 7}
    assert applied == {"pid": 0, "cpus": {4, 5, 6, 7}}
    with pytest.raises(ValueError, match="없는 코어"):
        pin("6-9")


def test_pin_is_ignored_where_unsupported(monkeypatch, capsys) -> None:
    monkeypatch.delattr(os, "sched_setaffinity", raising=False)
    assert pin("4-7") is None
    assert "리눅스 전용" in capsys.readouterr().out
