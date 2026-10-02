import csv
import pathlib

import pytest

from bench.stt_eval import FIELDS, evaluate, load_manifest, metrics, normalize, report
from services.audio_svc.stt import Transcript


class FakeEngine:
    """경로별로 정해 둔 받아쓰기 결과를 돌려준다 (음성 길이 1초, 인식 50 ms)."""

    def __init__(self, outputs: dict[str, str]) -> None:
        self.outputs = outputs

    def transcribe_file(self, path) -> Transcript:
        return Transcript(self.outputs[pathlib.Path(path).name], audio_ms=1000, stt_ms=50)


def write_manifest(path: pathlib.Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"speaker_id": "spk01", "mic": "pin", "split": "test", **r})


ROWS = [
    {"utt_id": "u1", "noise_type": "quiet", "path": "a.wav", "transcript": "자비스 후드 켜줘",
     "action_label": "<jarvis_1>(target=hood)<jarvis_end>"},
    {"utt_id": "u2", "noise_type": "hood", "path": "b.wav", "transcript": "자비스 2번 화구 꺼줘",
     "action_label": "<jarvis_2>(target=burner_2)<jarvis_end>"},
    {"utt_id": "u3", "noise_type": "hood", "path": "c.wav", "transcript": "오늘 뭐 먹지",
     "action_label": ""},
]  # fmt: skip
OUTPUTS = {
    "a.wav": "자비스 후드 켜 줘.",  # 띄어쓰기·문장부호만 다름 → CER 0, 정답
    "b.wav": "다비 2번 화구 꺼줘.",  # 호출어 오인식('스'까지 빠짐, 실제 마이크 출력) → 명령 안 됨
    "c.wav": "자비스 뭐 먹지",  # 호출어가 아닌데 호출로 받아씀 → 오호출
}


@pytest.fixture
def rows(tmp_path: pathlib.Path):
    manifest = tmp_path / "manifest.csv"
    write_manifest(manifest, ROWS)
    return evaluate(load_manifest(manifest, "test"), FakeEngine(OUTPUTS), tmp_path)


def test_normalize_ignores_spaces_and_punctuation() -> None:
    assert normalize("자비스, 후드 켜 줘.") == "자비스후드켜줘"


def test_metrics_overall(rows) -> None:
    m = metrics(rows)
    assert m["n"] == 3
    assert m["rtf"] == pytest.approx(0.05)
    assert m["wake_recall"] == pytest.approx(0.5)  # u1만 호출 인식
    assert m["false_wake"] == pytest.approx(1.0)  # u3 오호출
    assert m["action_exact"] == pytest.approx(0.5)  # u1 정답, u2 실패
    assert m["action_only"] == pytest.approx(0.5)
    assert m["parser_on_reference"] == pytest.approx(1.0)  # 정답 문장이면 파서는 둘 다 맞힘
    # 글자 오류: u2 '자'→'다'·'스' 빠짐, u3 '오늘'→'자비스'
    assert 0 < m["cer"] < 1


def test_report_groups_by_noise(rows) -> None:
    text = report(rows)
    assert "### 소음" in text
    assert "| hood | 2 |" in text and "| quiet | 1 |" in text
    assert "### 마이크" not in text  # 값이 하나뿐인 구분은 생략


def test_split_filter_and_label_validation(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "m.csv"
    write_manifest(manifest, [{**ROWS[0], "split": "train"}, ROWS[1]])
    assert [i["utt_id"] for i in load_manifest(manifest, "test")] == ["u2"]

    write_manifest(manifest, [{**ROWS[0], "action_label": "<jarvis_1>(target=fryer)<jarvis_end>"}])
    with pytest.raises(ValueError, match="target"):
        load_manifest(manifest, None)


def test_missing_column(tmp_path: pathlib.Path) -> None:
    manifest = tmp_path / "m.csv"
    manifest.write_text("utt_id,path\nu1,a.wav\n", encoding="utf-8")
    with pytest.raises(ValueError, match="열이 없음"):
        load_manifest(manifest, None)
