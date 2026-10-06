import csv
import pathlib

import numpy as np
import pytest

from bench.record_stt import Session, check, load_script
from bench.stt_eval import load_manifest
from common.function_call import parse_tokens

SCRIPT = pathlib.Path(__file__).parents[2] / "data/stt/script.csv"
VOICE = (np.sin(np.linspace(0, 2000, 16000)) * 0.3).astype(np.float32)  # 1초, 적당한 크기


class FakeRecorder:
    """녹음할 때마다 정해 둔 소리를 순서대로 돌려준다."""

    def __init__(self, takes: list[np.ndarray]) -> None:
        self.takes = list(takes)

    def record(self, wait) -> np.ndarray:
        wait()
        return self.takes.pop(0)


def session(tmp_path, keys, takes, script=None, **kw):
    answers = iter(keys)
    said: list[str] = []
    s = Session(
        script or [{"script_id": "s01", "category": "turn_on", "text": "자비스 후드 켜줘",
                    "action_label": "<jarvis_1>(target=hood)<jarvis_end>"},
                   {"script_id": "s02", "category": "no_wake", "text": "오늘 뭐 먹지",
                    "action_label": ""}],
        "spk01", "quiet", "pin", "test", tmp_path, tmp_path / "stt/manifest.csv",
        FakeRecorder(takes), ask=lambda _: next(answers), say=said.append, **kw,
    )  # fmt: skip
    return s, said


def test_records_and_writes_manifest(tmp_path: pathlib.Path) -> None:
    # 문장마다: Enter(시작) → Enter(끝) → Enter(저장)
    s, _ = session(tmp_path, ["", "", ""] * 2, [VOICE, VOICE])
    assert s.run() == 2
    assert (tmp_path / "stt/spk01/quiet_pin/s01.wav").exists()
    items = load_manifest(tmp_path / "stt/manifest.csv", "test")  # stt_eval이 그대로 읽는다
    assert [i["utt_id"] for i in items] == ["spk01_quiet_pin_s01", "spk01_quiet_pin_s02"]
    assert items[0]["path"] == "stt/spk01/quiet_pin/s01.wav"
    assert b"\r\n" not in (tmp_path / "stt/manifest.csv").read_bytes()  # 커밋할 파일이라 LF


def test_bad_take_is_retried_and_skip_and_quit(tmp_path: pathlib.Path) -> None:
    silent = np.zeros(16000, dtype=np.float32)
    # s01: 무음 → 경고 후 다시 → 저장 / s02: q로 그만
    s, said = session(tmp_path, ["", "", "", "", "", "q"], [silent, VOICE])
    assert s.run() == 1
    assert any("전혀 안 들어왔어요" in line for line in said)


def test_resume_skips_recorded_unless_redo(tmp_path: pathlib.Path) -> None:
    s, _ = session(tmp_path, ["", "", ""] * 2, [VOICE, VOICE])
    s.run()
    again, said = session(tmp_path, [], [])
    assert again.run() == 0 and "0/2문장 남음" in said[0]
    redo, _ = session(tmp_path, ["s", "s"], [], redo=True)
    assert redo.run() == 0  # 건너뛰기만 해도 기존 매니페스트는 그대로
    assert len(list(csv.DictReader((tmp_path / "stt/manifest.csv").open(encoding="utf-8")))) == 2


def test_rerecord_on_r(tmp_path: pathlib.Path) -> None:
    loud = (VOICE * 2).astype(np.float32)
    s, _ = session(tmp_path, ["", "", "r", "", "", "", "q"], [VOICE, loud])
    assert s.run() == 1  # 첫 녹음은 r로 버리고 두 번째를 저장


@pytest.mark.parametrize(
    ("samples", "problem"),
    [
        (np.zeros(3000, dtype=np.float32), "짧아요"),
        (np.zeros(16000, dtype=np.float32), "전혀"),
        (np.full(16000, 0.005, dtype=np.float32), "작아요"),
        (np.ones(16000, dtype=np.float32), "잘렸어요"),
        (VOICE, None),
    ],
)
def test_check(samples, problem) -> None:
    result = check(samples)
    assert result is None if problem is None else problem in result


def test_invalid_names_rejected(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="noise"):
        Session(
            [], "spk01", "kitchen", "pin", "test", tmp_path, tmp_path / "m.csv", FakeRecorder([])
        )
    with pytest.raises(ValueError, match="speaker"):
        Session(
            [], "홍길동", "quiet", "pin", "test", tmp_path, tmp_path / "m.csv", FakeRecorder([])
        )


def test_script_file_is_valid() -> None:
    assert b"\r\n" not in SCRIPT.read_bytes()
    rows = load_script(SCRIPT)
    assert len(rows) == 40
    assert len({r["script_id"] for r in rows}) == 40
    labels = [parse_tokens(r["action_label"]) for r in rows if r["action_label"]]
    assert {c["action"] for c in labels} == {
        "TURN_ON", "TURN_OFF", "SET_LEVEL", "SET_TIMER", "CANCEL_TIMER",
        "CHECK_STATUS", "CHECK_RISK", "EMERGENCY_STOP", "ASK_CLARIFY", "UNSUPPORTED",
    }  # fmt: skip
    assert sum(1 for r in rows if not r["action_label"]) == 6  # 호출어 없는 문장
