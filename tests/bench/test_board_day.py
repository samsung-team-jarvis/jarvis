"""보드 받은 날 도구 (INFRA-08). 보드가 아니어도 점검표·측정 계획·YOLO 시간 재기가 돈다."""

import pathlib

import numpy as np
import pytest

from bench import board_day
from tests.vision_svc.test_detect import outputs_with

pytest.importorskip("cv2")


def test_checks_report_every_item_without_crashing_off_board(tmp_path: pathlib.Path) -> None:
    checks = (
        board_day.check_board()
        + board_day.check_runtimes(tmp_path)
        + board_day.check_files(tmp_path)
        + board_day.check_system("mqtt://127.0.0.1:1")  # 닫힌 포트
    )
    by_name = {c.name: c for c in checks}
    assert by_name["MQTT 브로커"].ok is False
    assert by_name["llama-cpp-python (.venv-llm)"].ok is False  # tmp에는 가상환경이 없다
    assert all(by_name[n].ok is False for n in ("YOLO RKNN 모델", "LLM GGUF 모델"))
    assert all(c.ok is not False or c.fix for c in checks)  # 실패하면 고칠 방법이 있다


def test_print_checks_fails_only_on_failures(capsys) -> None:
    ok = [board_day.Check("a", True, "x"), board_day.Check("b", None, "권한 없음", "sudo …")]
    assert board_day.print_checks(ok) == 0
    assert board_day.print_checks(ok + [board_day.Check("c", False, "없음", "설치")]) == 1
    out = capsys.readouterr().out
    assert "→ 설치" in out and "→ sudo …" in out


class FakeEngine:
    name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def prepare(self, rgb: np.ndarray) -> np.ndarray:
        assert rgb.shape == (640, 640, 3)
        return rgb[None]

    def __call__(self, x: np.ndarray):
        self.calls += 1
        return outputs_with(10, 20, (2, 3, 4, 5), 0, 0.9)


def test_time_engine_splits_stages_and_skips_warmup() -> None:
    eng = FakeEngine()
    r = board_day.time_engine(eng, board_day.frames(None, 12), warmup=3)
    assert eng.calls == 15 and r["frames"] == 12
    for stage in ("pre_ms", "infer_ms", "post_ms", "total_ms"):
        assert r[stage]["mean"] >= 0 and r[stage]["p95"] >= 0
    assert r["fps"] > 0


def test_frames_from_folder_cycle(tmp_path: pathlib.Path) -> None:
    import cv2

    cv2.imwrite(str(tmp_path / "a.png"), np.zeros((10, 20, 3), np.uint8))
    got = board_day.frames(tmp_path, 3)
    assert len(got) == 3 and got[0].shape == (10, 20, 3)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        board_day.frames(empty, 1)


def test_measure_plan_and_dry_run(tmp_path: pathlib.Path, capsys) -> None:
    names = [name for name, _ in board_day.steps(tmp_path)]
    assert names == ["check", "vision", "llm", "stt"]
    pinned = [name for name, _ in board_day.steps(tmp_path, "4-7")]
    assert pinned == ["check", "vision", "llm", "llm_cpus", "stt"]
    assert "--cpus" in dict(board_day.steps(tmp_path, "4-7"))["llm_cpus"]
    args = type("A", (), {"out": tmp_path, "only": ["llm"], "dry_run": True, "llm_cpus": None})()
    assert board_day.measure(args) == 0
    out = capsys.readouterr().out
    assert "[llm]" in out and "--engine gguf" in out and "[stt]" not in out
    assert not (tmp_path / "summary.md").exists()


def test_agreement_pairs_people_by_box_overlap() -> None:
    def person(x: float, conf: float) -> dict:
        return {"cls": "person", "conf": conf, "bbox": [x, 0, x + 10, 10]}

    onnx = [[person(0, 0.9), person(50, 0.8)], [person(0, 0.7)]]
    rknn = [[person(1, 0.85), {"cls": "bus", "conf": 0.9, "bbox": [0, 0, 9, 9]}], []]
    a = board_day.agreement(onnx, rknn)
    assert (a["ref"], a["got"], a["matched"]) == (3, 1, 1)
    assert a["conf_diff_max"] == 0.05
