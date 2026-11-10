import itertools

import pytest

from bench import danger_path as dp
from common import messages
from services.recorder.store import SessionWriter
from tests.safety_guard.test_auto_stop import Kitchen


def record(tmp_path, monkeypatch, scenario) -> list:
    """가짜 가상 주방 위의 보드 서비스를 돌리며 모든 토픽을 녹화하고 다시 읽는다.

    봉투의 mono를 가짜 시계 + 발행 순서(1 µs씩)로 찍는다 — 실제 시계는 한 번에 지나가 버린다.
    """
    k = Kitchen()
    count = itertools.count()
    monkeypatch.setattr(messages.time, "monotonic", lambda: k.now + next(count) * 1e-6)
    writer = SessionWriter(tmp_path)
    k.bus.subscribe("#", writer.write)
    scenario(k)
    writer.close()
    assert len(list(tmp_path.glob("*.jsonl"))) > 1  # 서비스마다 세션이 다르다
    return dp.find_stops(dp.load([tmp_path]))


def overheat(k: Kitchen) -> None:
    k.run(1)
    k.say({"action": "SET_LEVEL", "target": "burner_1", "level": 3})
    k.run(60)


def unattended(k: Kitchen) -> None:
    k.run(1)
    k.say({"action": "TURN_ON", "target": "fryer"})
    k.person = False
    k.run(70)


def test_overheat_stop_is_chained_from_the_hot_reading(tmp_path, monkeypatch) -> None:
    stops = record(tmp_path, monkeypatch, overheat)
    assert [(s.kind, s.target) for s in stops] == [("과열", "burner_1")]
    s = stops[0]
    assert s.reading.payload["temperature_c"] >= 240
    assert s.trigger.payload["state"] == "DANGER"
    assert s.command.payload == {**s.command.payload, "cmd": "OFF", "target": "burner_1"}
    assert s.result.payload["ok"] is True
    seg = s.segments()
    assert all(seg[n] is not None and 0 <= seg[n] < 1 for n, _ in dp.SEGMENTS)  # 같은 1초 안
    assert seg["e2e"] == pytest.approx(sum(seg[n] for n, _ in dp.SEGMENTS[:4]), abs=0.01)


def test_unattended_stop_starts_from_the_judgement_and_shows_grace(tmp_path, monkeypatch) -> None:
    stops = record(tmp_path, monkeypatch, unattended)
    assert [(s.kind, s.target) for s in stops] == [("방치", "fryer")]
    s = stops[0]
    assert s.reading is None and s.segments()["to_fusion"] is None
    assert s.trigger.payload["evidence"]["absent_s"] >= 60
    assert s.unattended_s == 30.0  # 방치 판정 뒤 유예
    assert s.result.payload["ok"] is True
    assert "방치 1건" in dp.report(stops)


def test_cli_without_auto_stop_fails(tmp_path, capsys) -> None:
    (tmp_path / "empty.jsonl").write_text("", encoding="utf-8")
    assert dp.main([str(tmp_path)]) == 1
    assert "자동 차단이 없습니다" in capsys.readouterr().out
