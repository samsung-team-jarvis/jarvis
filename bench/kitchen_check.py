"""가상 주방 규격 자동 검사 (HW-24): 보드 역할로 `kitchen/*`를 주고받아 항목별 통과/실패를 낸다.

python -m bench.kitchen_check                          # 버스는 JARVIS_BUS (기본 mqtt://localhost:1883)
python -m bench.kitchen_check --bus mqtt://192.168.0.10:1883 --long --require-frames

검사 대상(Unity 또는 가짜 가상 주방)을 먼저 띄워 둔다. 이 스크립트가 보드 대신 생존 신호를 1초마다
보내고 명령을 발행하므로, **보드의 kitchen_gw는 함께 띄우지 않는다** (생존 신호·명령이 섞인다).
확인 목록은 recipes/unity-kitchen-link.md §5.2, 기준 동작은 services/kitchen_gw/fake_kitchen.py다.

- 약 15초 걸린다. `--long`은 265°C 자체 끄기까지 보느라 약 80초가 더 걸린다.
- 시작할 때와 끝날 때 모든 장치를 끈다.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from common import kitchen_link as link
from common.bus import Bus, connect

STATE_PERIOD_S = 5.0  # 상태는 바뀔 때마다 + 이 주기마다 (recipe §2-6)
STATE_GAP_LIMIT_S = STATE_PERIOD_S + 1.0
TEMP_TOLERANCE_C = 1.5  # 1초 주기가 조금 흔들려도 통과하게
CUTOFF_RANGE_S = (link.HEARTBEAT_TIMEOUT_S, link.HEARTBEAT_TIMEOUT_S + 1.5)
CUTOFF_EXPECT = (
    f"{CUTOFF_RANGE_S[0]:.0f}~{CUTOFF_RANGE_S[1]:.1f}초 뒤 가열 장치 OFF, "
    "safe_stop=true, 후드 그대로"
)
FPS_RANGE = (link.FRAME_FPS - 1.0, link.FRAME_FPS + 1.0)
LONG_WAIT_S = 100.0  # 25°C에서 세기 3 → 265°C까지 약 76초 (recipe §3)
POLL_S = 0.02


@dataclass(frozen=True)
class Check:
    name: str
    expect: str
    got: str
    ok: bool | None  # None = 해당 없음 (예: 화면을 보내지 않음)


def jpeg_size(data: bytes) -> tuple[int, int] | None:
    """JPEG 바이트 → (너비, 높이). SOF 마커만 읽는다 (그림을 풀지 않음). JPEG가 아니면 None."""
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            return None
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[i + 5 : i + 7], "big")
            width = int.from_bytes(data[i + 7 : i + 9], "big")
            return width, height
        i += 2 + length
    return None


class KitchenChecker:
    """보드 대신 생존 신호·명령을 보내고, 가상 주방이 보낸 확인·상태·온도·화면을 모은다."""

    def __init__(
        self,
        bus: Bus,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        first_seq: int | None = None,
    ) -> None:
        self.bus, self.clock, self.sleep = bus, clock, sleep
        self.heartbeat = True
        self._last_beat = float("-inf")
        self._seq = itertools.count(link.first_seq(time.time()) if first_seq is None else first_seq)
        self._lock = threading.Lock()
        self.acks: list[tuple[float, dict[str, Any]]] = []
        self.states: list[tuple[float, dict[str, Any]]] = []
        self.temps: list[tuple[float, dict[str, Any]]] = []
        self.frames: list[tuple[float, bytes]] = []
        self.bad: list[str] = []  # 규격에 맞지 않아 버린 메시지
        for topic, decode, into in (
            (link.TOPIC_ACK, link.decode_ack, self.acks),
            (link.TOPIC_STATE, link.decode_state, self.states),
            (link.TOPIC_TEMP, link.decode_temp, self.temps),
        ):
            bus.subscribe_raw(topic, self._collector(topic, decode, into))
        bus.subscribe_raw(link.TOPIC_FRAME, self._on_frame)

    def _collector(self, topic, decode, into):
        def handle(_topic: str, data: bytes) -> None:
            try:
                payload = decode(data)
            except link.LinkError as exc:
                with self._lock:
                    self.bad.append(f"{topic}: {exc}")
                return
            with self._lock:
                into.append((self.clock(), payload))

        return handle

    def _on_frame(self, _topic: str, data: bytes) -> None:
        with self._lock:
            self.frames.append((self.clock(), data))

    # --- 시간 · 발행 ---------------------------------------------------------------
    def wait(self, seconds: float, until: Callable[[], bool] | None = None) -> bool:
        """`seconds` 동안 (생존 신호를 보내며) 기다린다. `until`이 참이 되면 일찍 끝내고 True."""
        end = self.clock() + seconds
        while True:
            now = self.clock()
            if self.heartbeat and now - self._last_beat >= link.HEARTBEAT_PERIOD_S:
                self._last_beat = now
                self.bus.publish_raw(link.TOPIC_HEARTBEAT, link.encode({"alive": True}))
            if until is not None and until():
                return True
            if now >= end:
                return False
            self.sleep(POLL_S)

    def send(self, cmd: str, target: str, value: int, seq: int | None = None) -> tuple[int, float]:
        seq = next(self._seq) if seq is None else seq
        sent_at = self.clock()
        payload = {"seq": seq, "cmd": cmd, "target": target, "value": value}
        self.bus.publish_raw(link.TOPIC_CMD, json.dumps(payload).encode("utf-8"))
        return seq, sent_at

    def ack_for(
        self, seq: int, after: float, timeout: float
    ) -> tuple[dict[str, Any], float] | None:
        """`after` 뒤에 온 `seq`의 확인과 그때까지 걸린 초. `timeout` 안에 없으면 None."""

        def find():
            with self._lock:
                return next(((t, a) for t, a in self.acks if a["seq"] == seq and t >= after), None)

        self.wait(timeout, lambda: find() is not None)
        hit = find()
        return (hit[1], hit[0] - after) if hit else None

    def state_after(self, after: float, cond: Callable[[dict[str, Any]], bool], timeout: float):
        """`after` 뒤에 온 상태 중 `cond`를 만족하는 첫 상태 (시각, 상태). 없으면 None."""

        def find():
            with self._lock:
                return next(((t, s) for t, s in self.states if t >= after and cond(s)), None)

        self.wait(timeout, lambda: find() is not None)
        return find()

    def states_after(self, after: float) -> list[dict[str, Any]]:
        with self._lock:
            return [s for t, s in self.states if t >= after]

    # --- 검사 ----------------------------------------------------------------------
    def run(self, long: bool = False, require_frames: bool = False) -> list[Check]:
        start = self.clock()
        self.send("OFF", "all", 0)
        self.wait(1.5)
        results = [
            self.check_ack(),
            self.check_duplicate(),
            self.check_level(),
            self.check_reject_invalid(),
            self.check_temperature(),
            *self.check_heartbeat_loss(),
        ]
        if long:
            results.append(self.check_hard_limit())
        self.send("OFF", "all", 0)
        self.wait(0.5)
        results += [self.check_state_period(start), self.check_frames(require_frames)]
        results.append(
            Check(
                "규격 밖 메시지",
                "가상 주방이 보낸 ack · state · temp가 모두 규격에 맞음",
                "없음" if not self.bad else f"{len(self.bad)}건 — {self.bad[0]}",
                not self.bad,
            )
        )
        return results

    def _device(self, state: dict[str, Any], name: str) -> dict[str, Any]:
        return state["devices"].get(name, {})

    def check_ack(self) -> Check:
        seq, sent = self.send("ON", "hood", 1)
        hit = self.ack_for(seq, sent, link.ACK_TIMEOUT_S * 2)
        state = self.state_after(sent, lambda s: self._device(s, "hood").get("on") is True, 1.0)
        if hit is None:
            got, ok = f"{link.ACK_TIMEOUT_S * 2:.1f}초 안에 확인 없음", False
        else:
            ack, rtt = hit
            in_time = rtt <= link.ACK_TIMEOUT_S
            got = f"ok={ack['ok']}, 왕복 {rtt * 1000:.0f} ms" + ("" if in_time else " (0.5초 넘음)")
            ok = ack["ok"] is True and in_time
        got += ", 상태에 후드 켜짐 " + ("보고됨" if state else "없음")
        return Check(
            "명령 확인 (HW-16)",
            "ON hood → 0.5초 안에 ack ok=true, 상태에 후드 켜짐",
            got,
            ok and state is not None,
        )

    def check_duplicate(self) -> Check:
        seq, sent = self.send("OFF", "hood", 0)
        first = self.ack_for(seq, sent, 1.0)
        self.wait(0.3)
        _, resent = self.send("ON", "hood", 1, seq=seq)  # 같은 번호의 다른 명령 → 실행하면 안 된다
        again = self.ack_for(seq, resent, 1.0)
        self.wait(0.7)
        turned_on = any(self._device(s, "hood").get("on") for s in self.states_after(resent))
        ok = first is not None and first[0]["ok"] and again is not None and not turned_on
        got = (
            f"첫 확인 {'있음' if first else '없음'}, "
            f"다시 보낸 뒤 확인 {'있음' if again else '없음'}, "
            f"후드 {'다시 켜짐 (같은 번호를 또 실행)' if turned_on else '그대로 꺼짐'}"
        )
        return Check(
            "같은 seq 재실행 안 함 (HW-16)",
            "이미 처리한 seq가 다시 오면 장치는 그대로, ack만 다시",
            got,
            ok,
        )

    def check_level(self) -> Check:
        seq, sent = self.send("LEVEL", "burner_1", 2)
        hit = self.ack_for(seq, sent, 1.0)
        want = {"on": True, "level": 2}
        state = self.state_after(sent, lambda s: self._device(s, "burner_1") == want, 1.0)
        got = f"ack {'ok=' + str(hit[0]['ok']) if hit else '없음'}, 상태 " + (
            "burner_1 켜짐 · 세기 2" if state else "맞는 보고 없음"
        )
        return Check(
            "세기 바꾸기 (HW-16)",
            "LEVEL burner_1 2 → ack ok=true, 상태 {on: true, level: 2}",
            got,
            bool(hit and hit[0]["ok"] and state),
        )

    def check_reject_invalid(self) -> Check:
        seq, sent = self.send("ON", "oven", 1)  # 규격에 없는 장치
        hit = self.ack_for(seq, sent, 1.0)
        got = "확인 없음" if hit is None else f"ok={hit[0]['ok']}, reason={hit[0].get('reason')}"
        return Check(
            "규격 밖 명령 거절 (HW-16)",
            "모르는 target → 무시하지 않고 ack ok=false",
            got,
            hit is not None and hit[0]["ok"] is False,
        )

    def check_temperature(self) -> Check:
        """burner_1이 세기 2로 켜진 상태에서 온도 보고를 5초 모아 주기와 규칙을 본다."""
        start = self.clock()
        self.wait(5.0)
        with self._lock:
            readings = [
                (t, p["temperature_c"])
                for t, p in self.temps
                if t >= start and p["device_id"] == "burner_1"
            ]
        if len(readings) < 3:
            return Check(
                "가상 온도 (HW-19)",
                "burner_1 온도가 1초마다, 규칙대로 오름",
                f"5초 동안 burner_1 온도 {len(readings)}번",
                False,
            )
        gaps = [b[0] - a[0] for a, b in itertools.pairwise(readings)]
        errors = [
            abs(b[1] - link.next_temperature(a[1], 2, link.TEMP_PERIOD_S))
            for a, b in itertools.pairwise(readings)
        ]
        period_ok = all(0.5 <= g <= 1.5 for g in gaps)
        rule_ok = max(errors) <= TEMP_TOLERANCE_C and readings[-1][1] > readings[0][1]
        got = (
            f"{len(readings)}번, 간격 {min(gaps):.2f}~{max(gaps):.2f}초, "
            f"{readings[0][1]:.1f} → {readings[-1][1]:.1f}°C, 규칙과 차이 최대 {max(errors):.2f}°C"
        )
        return Check(
            "가상 온도 (HW-19)",
            f"burner_1 온도가 1초마다, 규칙대로 오름 (차이 ≤ {TEMP_TOLERANCE_C}°C)",
            got,
            period_ok and rule_ok,
        )

    def check_heartbeat_loss(self) -> list[Check]:
        seq, sent = self.send("ON", "hood", 1)
        self.ack_for(seq, sent, 1.0)
        self.wait(0.5)
        self.heartbeat = False
        last_beat = self._last_beat

        def cut(s):
            heaters_off = not any(self._device(s, h).get("on") for h in link.HEATERS)
            return s["safe_stop"] is True and heaters_off

        hit = self.state_after(last_beat, cut, CUTOFF_RANGE_S[1] + 1.0)
        if hit is None:
            loss = Check(
                "생존 신호 끊김 → 가열 장치 OFF (HW-18)",
                CUTOFF_EXPECT,
                f"{CUTOFF_RANGE_S[1] + 1.0:.1f}초 동안 가열 장치가 꺼진 상태 보고 없음",
                False,
            )
        else:
            after_s = hit[0] - last_beat
            hood_on = self._device(hit[1], "hood").get("on") is True
            in_range = CUTOFF_RANGE_S[0] - 0.2 <= after_s <= CUTOFF_RANGE_S[1]
            loss = Check(
                "생존 신호 끊김 → 가열 장치 OFF (HW-18)",
                CUTOFF_EXPECT,
                f"{after_s:.1f}초 뒤 꺼짐, 후드 {'켜진 채' if hood_on else '꺼짐'}",
                in_range and hood_on,
            )
        seq, sent = self.send("ON", "burner_2", 1)
        hit = self.ack_for(seq, sent, 1.0)
        refuse = Check(
            "끊긴 동안 가열 장치 켜기 거절 (HW-18)",
            "ON burner_2 → ack ok=false (no_heartbeat)",
            "확인 없음" if hit is None else f"ok={hit[0]['ok']}, reason={hit[0].get('reason')}",
            hit is not None and hit[0]["ok"] is False,
        )
        self.heartbeat = True
        self.wait(1.5)
        seq, sent = self.send("ON", "burner_2", 1)
        hit = self.ack_for(seq, sent, 1.0)
        recover = Check(
            "생존 신호가 돌아오면 다시 켜짐 (HW-18)",
            "ON burner_2 → ack ok=true",
            "확인 없음" if hit is None else f"ok={hit[0]['ok']}",
            hit is not None and hit[0]["ok"] is True,
        )
        self.send("OFF", "burner_2", 0)
        return [loss, refuse, recover]

    def check_hard_limit(self) -> Check:
        seq, sent = self.send("LEVEL", "burner_2", 3)
        self.ack_for(seq, sent, 1.0)

        def off(s):
            return s["safe_stop"] is True and not self._device(s, "burner_2").get("on")

        hit = self.state_after(sent, off, LONG_WAIT_S)
        with self._lock:
            temps = [
                p["temperature_c"]
                for t, p in self.temps
                if t >= sent and p["device_id"] == "burner_2"
            ]
        peak = max(temps, default=float("nan"))
        if hit is None:
            got, ok = f"{LONG_WAIT_S:.0f}초 동안 스스로 꺼지지 않음 (최고 {peak:.1f}°C)", False
        else:
            got = f"{hit[0] - sent:.0f}초 뒤 꺼짐, 최고 {peak:.1f}°C"
            ok = link.HARD_LIMIT_C - TEMP_TOLERANCE_C <= peak <= link.HARD_LIMIT_C + 5.0
        return Check(
            "265°C 자체 끄기 (HW-19, --long)",
            f"세기 3 → 약 76초 뒤 {link.HARD_LIMIT_C:.0f}°C에서 스스로 OFF, safe_stop=true",
            got,
            ok,
        )

    def check_state_period(self, start: float) -> Check:
        with self._lock:
            times = [t for t, _ in self.states if t >= start]
        end = self.clock()
        edges = [start, *times, end]
        gap = max(b - a for a, b in itertools.pairwise(edges))
        return Check(
            "상태 주기 보고 (HW-18)",
            f"상태가 바뀔 때 + {STATE_PERIOD_S:.0f}초마다 (간격 ≤ {STATE_GAP_LIMIT_S:.0f}초)",
            f"{len(times)}번, 가장 긴 간격 {gap:.1f}초",
            gap <= STATE_GAP_LIMIT_S,
        )

    def check_frames(self, required: bool) -> Check:
        expect = f"JPEG {link.FRAME_WIDTH}×{link.FRAME_HEIGHT}, 1초에 {link.FRAME_FPS}장"
        with self._lock:
            frames = list(self.frames)
        if len(frames) < 2:
            return Check(
                "인식용 화면 (HW-20)",
                expect,
                f"받은 화면 {len(frames)}장",
                False if required else None,
            )
        fps = (len(frames) - 1) / (frames[-1][0] - frames[0][0])
        sizes = {jpeg_size(data) for _, data in frames}
        size_ok = sizes == {(link.FRAME_WIDTH, link.FRAME_HEIGHT)}
        shown = ", ".join("JPEG 아님" if s is None else f"{s[0]}×{s[1]}" for s in sizes)
        return Check(
            "인식용 화면 (HW-20)",
            expect,
            f"{len(frames)}장, 1초에 {fps:.1f}장, 크기 {shown}",
            size_ok and FPS_RANGE[0] <= fps <= FPS_RANGE[1],
        )


def report(results: list[Check]) -> str:
    judged = [r for r in results if r.ok is not None]
    passed = sum(r.ok for r in judged)
    mark = {True: "통과", False: "**실패**", None: "해당 없음"}
    lines = [
        f"### 가상 주방 규격 검사: {passed} / {len(judged)} 통과",
        "",
        "| # | 항목 | 기대 | 결과 | 판정 |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r.name} | {r.expect} | {r.got} | {mark[r.ok]} |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="보드 역할로 가상 주방의 연결 규격을 검사한다")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--long", action="store_true", help="265°C 자체 끄기까지 (약 80초 더)")
    parser.add_argument("--require-frames", action="store_true", help="화면을 안 보내면 실패로")
    args = parser.parse_args()

    bus = connect(args.bus, client_id="kitchen_check")
    checker = KitchenChecker(bus)
    print("검사 중… (약 15초" + (" + 80초" if args.long else "") + ")", flush=True)
    try:
        results = checker.run(long=args.long, require_frames=args.require_frames)
    finally:
        bus.close()
    print(report(results))
    return 0 if all(r.ok is not False for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
