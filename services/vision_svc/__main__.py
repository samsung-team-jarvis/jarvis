"""vision_svc 실행 (VIS-08).

python -m services.vision_svc                              # 가상 주방 화면(kitchen/frame)
python -m services.vision_svc --input camera               # 노트북 카메라 (가상 주방이 없을 때)
python -m services.vision_svc --input data/frames/         # 이미지 폴더(또는 파일)를 한 번 흘림
python -m services.vision_svc detect photo.jpg             # 버스 없이 결과만
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import signal
import sys
import threading
import time

import numpy as np

from common import kitchen_link as link
from common.bus import connect
from common.messages import Envelope
from services.vision_svc import detect
from services.vision_svc.engine import THREADS, OnnxEngine
from services.vision_svc.service import DEFAULT_CLASSES, VisionService

DEFAULT_MODEL = "models/yolov8n_rknn_zoo.onnx"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}


def show(msg: Envelope) -> None:
    p = msg.payload
    names = ", ".join(f"{o['cls']} {o['conf']:.2f}" for o in p["objects"]) or "없음"
    print(
        f"[vision/objects] #{p['frame_id']} {names} "
        f"(전처리 {p['pre_ms']:.0f} · 추론 {p['npu_ms']:.0f} · 후처리 {p['post_ms']:.0f} ms)"
    )


def images(path: pathlib.Path) -> list[pathlib.Path]:
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    return [path]


def main() -> int:
    parser = argparse.ArgumentParser(description="화면에서 물체(기본: 사람)를 찾아 발행한다")
    sub = parser.add_subparsers(dest="cmd")
    d = sub.add_parser("detect", help="이미지 하나를 인식해 출력 (버스 없음)")
    d.add_argument("image")
    parser.add_argument(
        "--input",
        default="kitchen",
        help="kitchen(가상 주방 화면) | camera[:번호] | 이미지 폴더·파일",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="YOLOv8 ONNX (rknn_model_zoo 형식)")
    parser.add_argument("--classes", default=",".join(DEFAULT_CLASSES), help="발행할 COCO 클래스")
    parser.add_argument(
        "--fps", type=float, default=4.0, help="1초에 인식할 장수 (0이면 쉬지 않음)"
    )
    parser.add_argument("--threads", type=int, default=THREADS, help="추론 CPU 스레드")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--session", default=None, help="session_id (생략 시 s_<시각>)")
    parser.add_argument("--quiet", action="store_true", help="화면마다 출력하지 않음")
    args = parser.parse_args()

    import cv2

    engine = OnnxEngine(args.model, threads=args.threads)
    classes = [c.strip() for c in args.classes.split(",") if c.strip()]

    if args.cmd == "detect":
        bgr = cv2.imread(args.image)
        if bgr is None:
            print(f"이미지를 읽지 못했습니다: {args.image}")
            return 1
        tensor, box = detect.preprocess(bgr)
        found = detect.postprocess(engine(tensor), box, bgr.shape[1], bgr.shape[0])
        for o in found:
            print(json.dumps({**o, "bbox": [round(v) for v in o["bbox"]]}, ensure_ascii=False))
        return 0

    session_id = args.session or f"s_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    bus = connect(args.bus, client_id="vision_svc")
    service = VisionService(
        bus, session_id, engine, classes, on_objects=None if args.quiet else show
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    interval = 1.0 / args.fps if args.fps > 0 else 0.0

    latest: list[bytes] = []  # 가상 주방 화면: 가장 최근 것만 남긴다 (밀리면 건너뜀)
    lock = threading.Lock()
    camera = None
    files: list[pathlib.Path] = []
    if args.input == "kitchen":

        def on_frame(topic: str, data: bytes) -> None:
            with lock:
                latest[:] = [data]

        bus.subscribe_raw(link.TOPIC_FRAME, on_frame)
    elif args.input.startswith("camera"):
        index = int(args.input.partition(":")[2] or 0)
        camera = cv2.VideoCapture(index)
        if not camera.isOpened():
            print(f"카메라 {index}를 열지 못했습니다 (권한·번호 확인)")
            return 1
    else:
        files = images(pathlib.Path(args.input))
        if not files:
            print(f"이미지가 없습니다: {args.input}")
            return 1
    print(f"vision_svc 시작: input={args.input}, 클래스={classes}, {engine.name} (Ctrl+C로 종료)")

    try:
        while not stop.is_set():
            started = time.monotonic()
            bgr = None
            if args.input == "kitchen":
                with lock:
                    data = latest.pop() if latest else None
                if data is not None:
                    bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            elif camera is not None:
                ok, frame = camera.read()
                bgr = frame if ok else None
            else:
                if not files:
                    break
                bgr = cv2.imread(str(files.pop(0)))
            if bgr is not None:
                service.process(bgr)
            service.heartbeat()
            stop.wait(max(0.0, interval - (time.monotonic() - started)) if interval else 0.01)
    except KeyboardInterrupt:
        pass
    if camera is not None:
        camera.release()
    bus.close()
    print(f"OK: vision/objects {service.frame_id}건 발행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
