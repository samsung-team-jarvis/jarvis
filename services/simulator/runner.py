"""시나리오를 시간 순 메시지 목록으로 만들고 버스에 재생한다."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Callable

from common.bus import Bus
from common.messages import Envelope
from services.audio_svc.wake import is_wake
from services.simulator.scenario import Scenario, interpolate

SOURCE = "simulator"

# 클래스별 고정 bbox (640×640 기준) — 상황 판단 로직 개발용이라 위치는 의미 없음
_FAKE_BBOX = [100.0, 100.0, 300.0, 300.0]


@dataclasses.dataclass(frozen=True)
class Event:
    t: float  # 시나리오 시작 기준 초
    type: str
    payload_fn: Callable[[], dict]


def _ticks(duration: float, hz: float) -> list[float]:
    step = 1.0 / hz
    n = int(duration * hz) + 1
    return [round(i * step, 6) for i in range(n) if i * step <= duration]


def build_events(sc: Scenario) -> list[Event]:
    events: list[Event] = []

    for t in _ticks(sc.duration_s, sc.heartbeat_hz):
        events.append(Event(t, "system/heartbeat", lambda: {"alive": True}))

    if sc.sensor:
        s = sc.sensor
        for t in _ticks(sc.duration_s, s.hz):
            temp = round(interpolate(s.temperature_c, t), 2)
            cur = round(interpolate(s.current_a, t), 3)
            payload = {"device_id": s.device_id, "temperature_c": temp, "current_a": cur}
            events.append(Event(t, "sensor/reading", lambda p=payload: p))

    if sc.vision:
        v = sc.vision
        for frame_id, t in enumerate(_ticks(sc.duration_s, v.fps)):
            objects = [{"cls": c, "conf": 0.9, "bbox": list(_FAKE_BBOX)} for c in v.visible_at(t)]
            payload = {
                "objects": objects,
                "frame_id": frame_id,
                "pre_ms": 0.0,
                "npu_ms": 0.0,
                "post_ms": 0.0,
            }
            events.append(Event(t, "vision/objects", lambda p=payload: p))

    for t, text in sc.stt:
        if t > sc.duration_s:
            continue

        def stt_payload(text: str = text) -> dict:
            return {
                "text": text,
                "wake": is_wake(text),  # audio_svc와 같은 판정 (Q-08)
                "audio_ms": 0,
                "stt_ms": 0.0,
                "speech_end_mono": time.monotonic(),
            }

        events.append(Event(t, "stt/text", stt_payload))

    # 같은 시각이면 센서·비전 → 발화 순서가 아니라 생성 순서를 유지 (안정 정렬)
    return sorted(events, key=lambda e: e.t)


def play(
    sc: Scenario,
    bus: Bus,
    session_id: str,
    speed: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    on_event: Callable[[Envelope], None] | None = None,
) -> int:
    """시나리오를 재생하고 발행한 메시지 수를 돌려준다. speed=0이면 기다리지 않고 바로 보낸다."""
    events = build_events(sc)
    start = clock()
    for ev in events:
        if speed > 0:
            wait = start + ev.t / speed - clock()
            if wait > 0:
                sleep(wait)
        msg = Envelope.new(ev.type, SOURCE, ev.payload_fn(), session_id)
        bus.publish(msg)
        if on_event:
            on_event(msg)
    return len(events)
