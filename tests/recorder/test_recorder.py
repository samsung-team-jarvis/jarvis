import pathlib

import pytest

from common.bus import MemoryBus
from common.messages import Envelope, MessageError
from services.recorder.store import SessionWriter, read_session, session_filename, summarize
from services.simulator.runner import play
from services.simulator.scenario import load

SCENARIO = pathlib.Path(__file__).parents[2] / "services/simulator/scenarios/overheat.yaml"


def heartbeat(session: str) -> Envelope:
    return Envelope.new("system/heartbeat", "test", {"alive": True}, session)


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        ("s_20261012_01", "s_20261012_01.jsonl"),
        ("../../etc/passwd", "etc_passwd.jsonl"),
        ("a b/c", "a_b_c.jsonl"),
        ("", "unknown.jsonl"),
    ],
)
def test_session_filename_is_safe(session: str, expected: str) -> None:
    assert session_filename(session) == expected


def test_records_every_simulated_message(tmp_path: pathlib.Path) -> None:
    bus, writer = MemoryBus(), SessionWriter(tmp_path)
    bus.subscribe("#", writer.write)
    sent = play(load(SCENARIO), bus, "sim_test", speed=0)
    writer.close()

    path = tmp_path / "sim_test.jsonl"
    restored = list(read_session(path, strict=True))
    assert len(restored) == sent
    summary = summarize(path)
    assert summary["messages"] == sent
    assert summary["sessions"] == ["sim_test"]
    assert summary["by_topic"]["stt/text"] == 2


def test_sessions_go_to_separate_files(tmp_path: pathlib.Path) -> None:
    writer = SessionWriter(tmp_path)
    for session in ["s1", "s2", "s1"]:
        writer.write(heartbeat(session))
    writer.close()
    assert len(list(read_session(tmp_path / "s1.jsonl"))) == 2
    assert len(list(read_session(tmp_path / "s2.jsonl"))) == 1


def test_round_trip_keeps_envelope(tmp_path: pathlib.Path) -> None:
    writer = SessionWriter(tmp_path)
    msg = heartbeat("s")
    writer.write(msg)
    writer.close()
    assert next(read_session(tmp_path / "s.jsonl")) == msg


def test_truncated_last_line_is_skipped_unless_strict(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_text(heartbeat("s").to_json() + "\n" + '{"v": 1, "type": "sys', encoding="utf-8")
    assert len(list(read_session(path))) == 1
    with pytest.raises(MessageError):
        list(read_session(path, strict=True))
