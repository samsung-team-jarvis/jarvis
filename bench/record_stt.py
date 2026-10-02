"""STT 테스트 세트 녹음 도구 (STT-05).

python -m bench.record_stt --speaker spk01 --noise quiet --mic pin
python -m bench.record_stt --speaker spk01 --noise hood --mic pin --device 2 --split val

대본(data/stt/script.csv)의 문장을 하나씩 보여 주고, Enter로 녹음을 시작·끝낸다.
  저장: data/stt/<화자>/<소음>_<마이크>/<문장ID>.wav (16kHz mono 16-bit, git 제외)
  매니페스트: data/stt/manifest.csv에 한 줄씩 추가·갱신 (bench.stt_eval 입력 형식)
이미 녹음한 문장은 건너뛴다 (중간에 그만둬도 이어서 녹음). 다시 녹음은 --redo.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
import wave
from collections.abc import Callable
from typing import Protocol

import numpy as np

from bench.stt_eval import FIELDS

SAMPLE_RATE = 16000
NOISES = ("quiet", "hood", "frying", "mixed")
_ID = re.compile(r"^[A-Za-z0-9_-]+$")
MIN_SECONDS = 0.4
CLIP_LEVEL = 0.99


class Recorder(Protocol):
    def record(self, wait: Callable[[], object]) -> np.ndarray:
        """녹음을 시작하고 wait()가 돌아오면 멈춘다. float32 mono 16kHz."""


class MicRecorder:
    """마이크 스트림을 세션 동안 한 번만 열어 두고, 녹음 중일 때만 소리를 모은다.

    문장마다 스트림을 열고 닫으면 macOS CoreAudio에서 정지(AudioOutputUnitStop)가
    교착돼 도구가 멈춘 적이 있다 (#59).
    """

    def __init__(self, device: int | str | None = None) -> None:
        self.device = device
        self._stream = None
        self._chunks: list[np.ndarray] = []
        self._recording = False

    def _callback(self, data, frames, time_info, status) -> None:
        if self._recording:
            self._chunks.append(data[:, 0].copy())

    def record(self, wait: Callable[[], object]) -> np.ndarray:
        if self._stream is None:
            import sounddevice as sd

            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=self.device,
                callback=self._callback,
            )
            self._stream.start()
        self._chunks = []
        self._recording = True
        try:
            wait()
        finally:
            self._recording = False
        chunks, self._chunks = self._chunks, []
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()  # 세션이 끝날 때 한 번만
            self._stream = None


def write_wav(path: pathlib.Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def check(samples: np.ndarray) -> str | None:
    """녹음이 이상하면 이유, 괜찮으면 None."""
    if len(samples) < MIN_SECONDS * SAMPLE_RATE:
        return (
            f"너무 짧아요 ({len(samples) / SAMPLE_RATE:.1f}초). Enter를 누른 뒤 말하고 다시 Enter."
        )
    peak = float(np.abs(samples).max())
    if peak == 0.0:
        return (
            "소리가 전혀 안 들어왔어요 (입력이 모두 0). Mac이면 시스템 설정 > 개인정보 보호 및 "
            "보안 > 마이크에서 터미널을 허용하고 터미널을 다시 실행하세요. 또는 --device 확인."
        )
    if peak < 0.02:
        return f"소리가 너무 작아요 (최대 {peak:.3f}). 마이크를 가까이 하거나 입력 음량을 올리세요."
    if peak >= CLIP_LEVEL:
        return "소리가 너무 커서 잘렸어요(클리핑). 마이크를 조금 멀리 하세요."
    return None


def load_script(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def upsert_manifest(path: pathlib.Path, row: dict[str, str]) -> None:
    rows: dict[str, dict[str, str]] = {}
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            rows = {r["utt_id"]: r for r in csv.DictReader(f)}
    rows[row["utt_id"]] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")  # git에서 CRLF 경고 없게
        w.writeheader()
        for key in sorted(rows):
            w.writerow(rows[key])


class Session:
    def __init__(
        self,
        script: list[dict[str, str]],
        speaker: str,
        noise: str,
        mic: str,
        split: str,
        root: pathlib.Path,
        manifest: pathlib.Path,
        recorder: Recorder,
        ask: Callable[[str], str] = input,
        say: Callable[[str], None] = print,
        redo: bool = False,
    ) -> None:
        for name, value in (("speaker", speaker), ("mic", mic), ("split", split)):
            if not _ID.match(value):
                raise ValueError(f"{name}는 영문·숫자·_- 만: {value!r}")
        if noise not in NOISES:
            raise ValueError(f"noise는 {NOISES} 중 하나: {noise!r}")
        self.script, self.speaker, self.noise, self.mic, self.split = (
            script,
            speaker,
            noise,
            mic,
            split,
        )
        self.root, self.manifest, self.recorder = root, manifest, recorder
        self.ask, self.say, self.redo = ask, say, redo
        self.saved = 0

    def rel_path(self, script_id: str) -> str:
        return f"stt/{self.speaker}/{self.noise}_{self.mic}/{script_id}.wav"

    def _recorded(self, script_id: str) -> bool:
        return (self.root / self.rel_path(script_id)).exists()

    def run(self) -> int:
        todo = [r for r in self.script if self.redo or not self._recorded(r["script_id"])]
        self.say(
            f"{self.speaker} · {self.noise} · {self.mic}: {len(todo)}/{len(self.script)}문장 남음"
        )
        try:
            for i, row in enumerate(todo, 1):
                if not self._one(i, len(todo), row):
                    break
        finally:
            if hasattr(self.recorder, "close"):
                self.recorder.close()
        self.say(f"저장 {self.saved}건 → {self.manifest}")
        return self.saved

    def _one(self, i: int, total: int, row: dict[str, str]) -> bool:
        """한 문장 녹음. 그만두면 False."""
        self.say(f"\n[{i}/{total}] {row['script_id']}  «{row['text']}»")
        while True:
            cmd = self.ask("  Enter=녹음 시작 · s=건너뛰기 · q=그만 > ").strip().lower()
            if cmd == "q":
                return False
            if cmd == "s":
                return True
            samples = self.recorder.record(lambda: self.ask("  ● 녹음 중… 다 말했으면 Enter "))
            problem = check(samples)
            if problem:
                self.say(f"  ! {problem} 다시 녹음합니다.")
                continue
            self.say(f"  {len(samples) / SAMPLE_RATE:.1f}초 · 최대 {np.abs(samples).max():.2f}")
            again = self.ask("  Enter=저장 · r=다시 녹음 > ").strip().lower()
            if again == "r":
                continue
            self._save(row, samples)
            return True

    def _save(self, row: dict[str, str], samples: np.ndarray) -> None:
        rel = self.rel_path(row["script_id"])
        write_wav(self.root / rel, samples)
        upsert_manifest(
            self.manifest,
            {
                "utt_id": f"{self.speaker}_{self.noise}_{self.mic}_{row['script_id']}",
                "speaker_id": self.speaker,
                "noise_type": self.noise,
                "mic": self.mic,
                "path": rel,
                "transcript": row["text"],
                "action_label": row["action_label"],
                "split": self.split,
            },
        )
        self.saved += 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="STT 테스트 세트를 녹음한다 (대본 → wav + 매니페스트)"
    )
    parser.add_argument("--speaker", required=True, help="화자 ID (예: spk01, 이름 대신)")
    parser.add_argument("--noise", required=True, choices=NOISES)
    parser.add_argument("--mic", required=True, help="마이크 종류 (예: pin, webcam)")
    parser.add_argument("--split", default="test", help="화자 단위 split (기본 test)")
    parser.add_argument("--device", default=None, help="마이크 장치 번호·이름")
    parser.add_argument("--script", type=pathlib.Path, default=pathlib.Path("data/stt/script.csv"))
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("data"))
    parser.add_argument(
        "--manifest", type=pathlib.Path, default=pathlib.Path("data/stt/manifest.csv")
    )
    parser.add_argument("--redo", action="store_true", help="이미 녹음한 문장도 다시")
    args = parser.parse_args()

    device = int(args.device) if args.device and args.device.isdigit() else args.device
    try:
        session = Session(
            load_script(args.script), args.speaker, args.noise, args.mic, args.split,
            args.root, args.manifest, MicRecorder(device), redo=args.redo,
        )  # fmt: skip
        session.run()
    except (OSError, ValueError) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n중단 — 저장한 문장까지는 남아 있어요. 같은 명령으로 이어서 녹음합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
