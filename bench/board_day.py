"""보드 받은 날 (INFRA-08): 설치 점검 → 최종 측정을 명령 몇 줄로.

python -m bench.board_day check              # 점검표: 보드·NPU·런타임·모델·브로커·카메라·온도
python -m bench.board_day vision --compare   # YOLO 전처리/NPU/후처리 ms (+ 같은 화면으로 ONNX CPU)
python -m bench.board_day measure --dry-run  # 실행할 측정 명령만 보기
python -m bench.board_day measure            # 측정을 순서대로 → runs/board/<시각>/ (로그·summary)

- 시연 구성 동시 구동(BOARD-08)·장시간 구동(BOARD-09)은 마이크·카메라·사람이 필요해 여기서
  돌리지 않는다. 절차: recipes/board-setup.md "받은 날 순서".
- `vision`에 사진 폴더를 주지 않으면 무작위 화면으로 잰다 — 속도만 보는 것이다 (물체 수가 적어
  후처리가 실제보다 짧을 수 있다). 사람이 있는 화면으로 재려면 `--images <폴더>`.
"""

from __future__ import annotations

import argparse
import ctypes.util
import dataclasses
import datetime
import glob
import importlib.util
import json
import os
import pathlib
import platform
import shlex
import socket
import statistics
import subprocess
import sys
import time
import urllib.parse

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
RKNN_MODEL = "models/yolov8n_coco_i8.rknn"  # training/convert/docker_rknn_yolo.sh 결과를 복사
ONNX_MODEL = "models/yolov8n_rknn_zoo.onnx"
GGUF_MODEL = "runs/llm/llm_qwen3-0.6b_jarvis_v4-q8_0.gguf"  # launch_demo.yaml과 같은 모델
LLM_PYTHON = ".venv-llm/bin/python"
STT_DIR = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
VAD_MODEL = "models/silero_vad.onnx"
TTS_DIR = "models/vits-mimic3-ko_KO-kss_low"
STT_MANIFEST = "data/stt/manifest.csv"
RKNN_PYTHON = ((3, 7), (3, 12))  # rknn-toolkit-lite2 2.3.2가 지원하는 Python


@dataclasses.dataclass
class Check:
    name: str
    ok: bool | None  # None = 확인 못 함 (권한·해당 없음)
    detail: str
    fix: str = ""


def _read(path: str) -> str | None:
    try:
        return pathlib.Path(path).read_text(errors="replace").strip("\x00\n ")
    except OSError:
        return None


def _module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def check_board() -> list[Check]:
    model = _read("/proc/device-tree/model") or ""
    is_board = "rk3588" in model.lower() or "orange pi" in model.lower()
    out = [
        Check(
            "보드",
            is_board,
            model or f"{platform.system()} {platform.machine()} (보드 아님)",
            "Orange Pi 5 Plus(RK3588)에서 실행",
        ),
        Check("CPU 구조", platform.machine() == "aarch64", platform.machine(), "aarch64 보드에서"),
    ]
    v = sys.version_info[:2]
    lo, hi = RKNN_PYTHON
    out.append(
        Check(
            "Python (rknn-toolkit-lite2)",
            lo <= v <= hi,
            platform.python_version(),
            f"Python {lo[0]}.{lo[1]}~{hi[0]}.{hi[1]}",
        )
    )
    version = _read("/sys/kernel/debug/rknpu/version")
    if version is None and os.path.exists("/sys/kernel/debug/rknpu"):
        out.append(
            Check("NPU 드라이버", None, "권한 없음", "sudo cat /sys/kernel/debug/rknpu/version")
        )
    else:
        out.append(
            Check("NPU 드라이버", version is not None, version or "없음", "보드 이미지(커널) 확인")
        )
    lib = ctypes.util.find_library("rknnrt") or next(
        (p for p in ("/usr/lib/librknnrt.so", "/usr/lib64/librknnrt.so") if os.path.exists(p)),
        None,
    )
    out.append(Check("librknnrt.so", lib is not None, lib or "없음", "recipes/board-setup.md §4"))
    out.append(
        Check(
            "rknn-toolkit-lite2",
            _module("rknnlite"),
            "rknnlite",
            "pip install rknn_toolkit_lite2-2.3.2-…aarch64.whl (board-setup §4)",
        )
    )
    return out


def check_runtimes(root: pathlib.Path = ROOT) -> list[Check]:
    out = []
    for name, module, fix in (
        ("onnxruntime", "onnxruntime", "pip install -r requirements.txt"),
        ("OpenCV", "cv2", "pip install -r requirements.txt"),
        ("sherpa-onnx (STT·TTS)", "sherpa_onnx", "pip install -r requirements.txt"),
        ("sounddevice (마이크·스피커)", "sounddevice", "sudo apt install libportaudio2"),
        ("paho-mqtt (버스)", "paho", "pip install -r requirements.txt"),
    ):
        out.append(Check(name, _module(module), module, fix))
    py = root / LLM_PYTHON
    if not py.exists():
        out.append(Check("llama-cpp-python (.venv-llm)", False, "없음", "LLM 가상환경 만들기"))
    else:
        r = subprocess.run(
            [str(py), "-c", "import llama_cpp; print(llama_cpp.__version__)"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out.append(
            Check(
                "llama-cpp-python (.venv-llm)",
                r.returncode == 0,
                r.stdout.strip() or r.stderr.strip()[-80:],
                "pip install llama-cpp-python==0.3.36 (versions.md)",
            )
        )
    return out


def check_files(root: pathlib.Path = ROOT) -> list[Check]:
    files = (
        ("YOLO RKNN 모델", RKNN_MODEL, "Mac에서 docker_rknn_yolo.sh 결과를 복사"),
        ("YOLO ONNX 모델", ONNX_MODEL, "services/vision_svc/README.md 모델 받기"),
        ("LLM GGUF 모델", GGUF_MODEL, "Mac의 runs/llm/에서 복사"),
        ("STT 모델 (SenseVoice)", STT_DIR, "Mac의 models/에서 복사"),
        ("VAD 모델", VAD_MODEL, "Mac의 models/에서 복사"),
        ("TTS 모델 (VITS)", TTS_DIR, "Mac의 models/에서 복사"),
        ("STT 평가 데이터", STT_MANIFEST, "Mac의 data/stt/에서 복사"),
    )
    return [Check(name, (root / path).exists(), path, fix) for name, path, fix in files]


def check_system(bus_url: str | None = None) -> list[Check]:
    url = urllib.parse.urlparse(bus_url or os.environ.get("JARVIS_BUS", "mqtt://localhost:1883"))
    host, port = url.hostname or "localhost", url.port or 1883
    try:
        with socket.create_connection((host, port), timeout=1.0):
            broker = True
    except OSError:
        broker = False
    out = [Check("MQTT 브로커", broker, f"{host}:{port}", "sudo apt install mosquitto")]
    if platform.system() == "Linux":
        cams = sorted(glob.glob("/dev/video*"))
        out.append(Check("카메라", bool(cams), ", ".join(cams) or "없음", "USB 웹캠 연결"))
        temps = [_read(p) for p in glob.glob("/sys/class/thermal/thermal_zone*/temp")]
        temps_c = [int(t) / 1000 for t in temps if t and t.lstrip("-").isdigit()]
        out.append(
            Check(
                "SoC 온도",
                bool(temps_c) and max(temps_c) < 80,
                f"최고 {max(temps_c):.1f}°C" if temps_c else "읽지 못함",
                "방열판·팬 확인 (80°C 이상)",
            )
        )
        mem = _read("/proc/meminfo") or ""
        total = next((ln.split()[1] for ln in mem.splitlines() if ln.startswith("MemTotal")), "")
        out.append(
            Check("RAM", bool(total), f"{int(total) / 1e6:.1f} GB" if total else "읽지 못함")
        )
    else:
        out.append(Check("카메라·온도·RAM", None, f"{platform.system()} — 보드에서 확인"))
    return out


def print_checks(checks: list[Check]) -> int:
    mark = {True: "통과", False: "실패", None: "확인 못 함"}
    for c in checks:
        fix = f"  → {c.fix}" if c.ok is not True and c.fix else ""
        print(f"[{mark[c.ok]:^6}] {c.name}: {c.detail}{fix}")
    failed = sum(c.ok is False for c in checks)
    print(f"\n통과 {sum(c.ok is True for c in checks)} · 실패 {failed} · 확인 못 함 "
          f"{sum(c.ok is None for c in checks)}")  # fmt: skip
    return 1 if failed else 0


# ── YOLO 속도 ─────────────────────────────────────────────────────────


def frames(images: pathlib.Path | None, n: int) -> list[np.ndarray]:
    """사진 폴더(돌려 쓰기) 또는 무작위 640×360 화면 n장."""
    if images is None:
        rng = np.random.default_rng(0)
        return [rng.integers(0, 256, (360, 640, 3), dtype=np.uint8) for _ in range(n)]
    import cv2

    paths = sorted(p for p in images.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    loaded = [img for p in paths if (img := cv2.imread(str(p))) is not None]
    if not loaded:
        raise FileNotFoundError(f"사진이 없습니다: {images}")
    return [loaded[i % len(loaded)] for i in range(n)]


def _stats(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {"mean": round(statistics.fmean(values), 2), "p95": round(p95, 2)}


MATCH_IOU = 0.5  # 이만큼 겹치면 두 엔진이 같은 물체를 찾은 것으로 본다


def _iou(a: list[float], b: list[float]) -> float:
    w = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    h = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def agreement(ref: list[list[dict]], got: list[list[dict]], cls: str = "person") -> dict:
    """화면마다 같은 클래스의 물체를 상자 겹침으로 짝짓는다 (ref = ONNX CPU, got = RKNN NPU)."""
    n_ref = n_got = matched = 0
    conf_diff: list[float] = []
    for r_frame, g_frame in zip(ref, got, strict=True):
        rs = [d for d in r_frame if d["cls"] == cls]
        gs = [d for d in g_frame if d["cls"] == cls]
        n_ref, n_got, used = n_ref + len(rs), n_got + len(gs), set()
        for r in rs:
            best, best_iou = None, MATCH_IOU
            for i, g in enumerate(gs):
                if i not in used and (iou := _iou(r["bbox"], g["bbox"])) >= best_iou:
                    best, best_iou = i, iou
            if best is not None:
                used.add(best)
                matched += 1
                conf_diff.append(abs(r["conf"] - gs[best]["conf"]))
    return {
        "class": cls,
        "ref": n_ref,
        "got": n_got,
        "matched": matched,
        "conf_diff_max": round(max(conf_diff, default=0.0), 3),
    }


def time_engine(engine, images: list[np.ndarray], warmup: int = 5) -> dict:
    """화면마다 전처리(letterbox + 엔진 입력 변환) / 추론 / 후처리 ms, 찾은 물체(`found`)."""
    from services.vision_svc import detect

    pre, infer, post, found = [], [], [], []
    for i, bgr in enumerate([*images[:warmup], *images]):
        t0 = time.perf_counter()
        rgb, box = detect.letterbox(bgr)
        x = engine.prepare(rgb)
        t1 = time.perf_counter()
        outputs = engine(x)
        t2 = time.perf_counter()
        objects = detect.postprocess(outputs, box, bgr.shape[1], bgr.shape[0])
        t3 = time.perf_counter()
        if i >= warmup:  # 첫 몇 장은 런타임 준비가 섞여 뺀다
            pre.append((t1 - t0) * 1000)
            infer.append((t2 - t1) * 1000)
            post.append((t3 - t2) * 1000)
            found.append(objects)
    total = [a + b + c for a, b, c in zip(pre, infer, post, strict=True)]
    return {
        "engine": engine.name,
        "frames": len(total),
        "pre_ms": _stats(pre),
        "infer_ms": _stats(infer),
        "post_ms": _stats(post),
        "total_ms": _stats(total),
        "fps": round(1000 / statistics.fmean(total), 1),
        "found": found,
    }


def vision(args: argparse.Namespace) -> int:
    from services.vision_svc import engine as engines

    model = args.model or (RKNN_MODEL if (ROOT / RKNN_MODEL).exists() else ONNX_MODEL)
    models = [model] + ([ONNX_MODEL] if args.compare and model != ONNX_MODEL else [])
    images = frames(args.images, args.n)
    results = []
    for m in models:
        eng = engines.load(str(ROOT / m), threads=args.threads, core=args.npu_core)
        r = time_engine(eng, images) | {"model": m}
        if hasattr(eng, "release"):
            eng.release()
        results.append(r)
        print(
            f"{r['engine']} ({m}, {r['frames']}장): 전처리 {r['pre_ms']['mean']} · "
            f"추론 {r['infer_ms']['mean']} (p95 {r['infer_ms']['p95']}) · "
            f"후처리 {r['post_ms']['mean']} ms → 합계 {r['total_ms']['mean']} ms, {r['fps']} fps"
        )
    source = str(args.images) if args.images else "무작위 화면 (속도만)"
    report = {"images": source, "machine": platform.platform()}
    if len(results) == 2 and args.images:  # 같은 사진에서 NPU 모델이 ONNX와 같은 사람을 찾는가
        a = agreement(results[1]["found"], results[0]["found"])
        report["agreement"] = a
        print(
            f"사람: ONNX {a['ref']} · {results[0]['engine']} {a['got']} · 짝 {a['matched']} "
            f"(상자 겹침 {MATCH_IOU} 이상), 점수 차 최대 {a['conf_diff_max']}"
        )
    report["results"] = [{k: v for k, v in r.items() if k != "found"} for r in results]
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


# ── 측정 일괄 ─────────────────────────────────────────────────────────


def steps(out: pathlib.Path, llm_cpus: str | None = None) -> list[tuple[str, list[str]]]:
    """(이름, 명령). 저장소 루트에서 실행한다. llm_cpus가 있으면 큰 코어 고정 LLM도 (LLM-19)."""
    py = sys.executable
    llm = [LLM_PYTHON, "-m", "bench.llm_eval", "--engine", "gguf", "--model", GGUF_MODEL,
           "--split", "test"]  # fmt: skip
    pinned = [("llm_cpus", [*llm, "--cpus", llm_cpus, "--csv", str(out / "llm_test_cpus.csv")])]
    return [
        ("check", [py, "-m", "bench.board_day", "check"]),
        ("vision", [py, "-m", "bench.board_day", "vision", "--compare",
                    "--json", str(out / "vision.json")]),
        ("llm", [*llm, "--csv", str(out / "llm_test.csv")]),
        *(pinned if llm_cpus else []),
        ("stt", [py, "-m", "bench.stt_eval", STT_MANIFEST, "--split", "val",
                 "--csv", str(out / "stt_val.csv")]),
    ]  # fmt: skip


def soc_temp() -> str:
    temps = [_read(p) for p in glob.glob("/sys/class/thermal/thermal_zone*/temp")]
    temps_c = [int(t) / 1000 for t in temps if t and t.lstrip("-").isdigit()]
    return f"{max(temps_c):.1f}°C" if temps_c else "읽지 못함"


def measure(args: argparse.Namespace) -> int:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = args.out or ROOT / "runs" / "board" / stamp
    plan = [s for s in steps(out, args.llm_cpus) if not args.only or s[0] in args.only]
    if args.dry_run:
        for name, argv in plan:
            print(f"[{name}] {shlex.join(argv)}")
        return 0
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, argv in plan:
        print(f"\n=== {name}: {shlex.join(argv)}", flush=True)
        temp_before = soc_temp()
        started = time.monotonic()
        lines: list[str] = []
        with open(out / f"{name}.log", "w", encoding="utf-8") as log:
            proc = subprocess.Popen(
                argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
            )
            for line in proc.stdout:
                print(line, end="", flush=True)
                log.write(line)
                lines.append(line.rstrip())
            code = proc.wait()
        rows.append((name, code, time.monotonic() - started, temp_before, soc_temp(), lines[-6:]))
    summary = [f"# 보드 측정 {stamp}", "", f"- {platform.platform()}", ""]
    summary += ["| 단계 | 종료 코드 | 걸린 시간 | SoC 온도 (전 → 후) |", "|---|---|---|---|"]
    summary += [f"| {n} | {c} | {s:.0f} s | {a} → {b} |" for n, c, s, a, b, _ in rows]
    for n, *_, tail in rows:
        summary += ["", f"## {n} (마지막 줄)", "", "```text", *tail, "```"]
    (out / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"\n결과: {out}/summary.md")
    return 1 if any(c for _, c, *_ in rows) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="보드 점검·최종 측정 (INFRA-08)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="점검표")
    c.add_argument("--bus", default=None, help="브로커 (생략 시 JARVIS_BUS)")
    v = sub.add_parser("vision", help="YOLO 속도")
    v.add_argument("--model", default=None, help=f"기본: {RKNN_MODEL} (없으면 ONNX)")
    v.add_argument("--compare", action="store_true", help="같은 화면으로 ONNX CPU도")
    v.add_argument("--images", type=pathlib.Path, default=None, help="사진 폴더 (생략 시 무작위)")
    v.add_argument("-n", type=int, default=100, help="화면 수")
    v.add_argument("--threads", type=int, default=2, help="ONNX CPU 스레드 (시연과 같게)")
    v.add_argument("--npu-core", default="0", help="RKNN NPU 코어")
    v.add_argument("--json", type=pathlib.Path, default=None)
    m = sub.add_parser("measure", help="측정 일괄")
    m.add_argument("--dry-run", action="store_true", help="명령만 출력")
    m.add_argument("--only", nargs="*", help="이 단계만 (check vision llm llm_cpus stt)")
    m.add_argument("--llm-cpus", default=None, help="LLM을 이 코어에 고정해 한 번 더 (예: 4-7)")
    m.add_argument("--out", type=pathlib.Path, default=None)
    args = parser.parse_args()

    if args.cmd == "check":
        return print_checks(
            check_board() + check_runtimes() + check_files() + check_system(args.bus)
        )
    if args.cmd == "vision":
        return vision(args)
    return measure(args)


if __name__ == "__main__":
    sys.exit(main())
