"""State Machine v1 (FUS-08): 온도·화면·장치 상태·음성 근거 → 주방 State.

판정 기준: docs/decisions/2026-11-09-state-rules.md (interfaces §2.3).
1초마다, 위에서부터 먼저 맞는 것:
SAFE_STOP > DANGER > UNATTENDED > COOKING > PREHEAT > IDLE.

- 근거는 `update()`로만 바뀐다. `state()`·`snapshot()`은 읽기만 한다 — 같은 근거와 시각이면
  몇 번을 불러도 같은 답이다 (DANGER 해제 기준·SAFE_STOP 유지도 근거가 들어올 때 갱신).
- 근거마다 들어온 시각을 기억하고, 오래된 근거는 믿지 않는다 (stale context):
  화면이 끊기면 사람이 없는 것으로, 온도가 끊긴 장치는 온도를 모르는 것으로 본다.
- 버스·시계와 무관하다. 시각 `t`는 부르는 쪽이 준다 (서비스는 보드 단조 시계, 평가는 시나리오 초).
"""

from __future__ import annotations

import dataclasses
from typing import Any

from common.kitchen_link import HEATERS
from services.safety_guard.emergency import is_emergency

# 판정 기준 (decision 2026-11-09)
DANGER_C = 240.0
DANGER_EXIT_C = 230.0  # DANGER는 모두 이 아래로 내려가야 풀린다 (경계에서 깜빡이지 않게)
WARN_C = 200.0
COOK_C = 100.0  # 예열/조리 경계이자 SAFE_STOP 해제 온도
UNATTENDED_S = 30.0
UNATTENDED_WARN_S = 10.0

# 근거를 믿는 시간 (v1 값 — 보드·가상 주방에서 써 보고 조정한다)
VISION_STALE_S = 2.0  # 화면 2~4장/초 — 2초 동안 한 장도 없으면 끊긴 것
TEMP_STALE_S = 3.0  # 온도 1초에 1번 — 3번 빠지면 끊긴 것
DEVICES_STALE_S = 12.0  # 장치 상태 5초에 1번 — 2번 빠지면 끊긴 것 (표시만, 마지막 값 유지)

RISKY = frozenset({"DANGER", "UNATTENDED"})


@dataclasses.dataclass
class _Heater:
    on: bool = False
    level: int = 0
    temperature_c: float | None = None
    temp_at: float | None = None
    hot: bool = False  # DANGER 히스테리시스: 240°C 이상에서 켜지고 230°C 아래에서 꺼진다


class StateMachine:
    def __init__(self) -> None:
        self.heaters = {h: _Heater() for h in HEATERS}
        self.devices_at: float | None = None
        self.kitchen_safe_stop = False  # 가상 주방이 마지막으로 알려 준 safe_stop
        self.safe_stop: str | None = None  # SAFE_STOP 원인: "emergency" | "kitchen" | None
        self.heating_since: float | None = None  # 가열 장치가 (하나라도) 켜진 시각
        self.vision_at: float | None = None  # 마지막 화면 시각
        # 사람이 안 보이기 시작한 시각. None = 마지막 화면에 사람이 있음. 처음에는 본 적 없음(-inf)
        self.absent_since: float | None = float("-inf")

    # ── 근거 ──────────────────────────────────────────────────────────

    def update(self, t: float, topic: str, payload: dict[str, Any]) -> None:
        if topic == "device/state":
            self._on_devices(t, payload)
        elif topic == "sensor/reading":
            self._on_reading(t, payload)
        elif topic == "vision/objects":
            self._on_vision(t, payload)
        elif topic == "stt/text":
            if is_emergency(payload["text"], payload["wake"]):  # Guard 빠른 경로와 같은 판단
                self.safe_stop = "emergency"
        elif topic == "guard/decision":
            call = payload.get("call") or {}
            if call.get("action") == "EMERGENCY_STOP" and payload.get("decision") == "ALLOW":
                self.safe_stop = "emergency"  # 명령 해석을 거친 긴급 정지
        self._release_safe_stop(t)

    def _on_devices(self, t: float, payload: dict[str, Any]) -> None:
        was_heating = self._heating()
        for name, dev in payload["devices"].items():
            if name in self.heaters:
                self.heaters[name].on = bool(dev["on"])
                self.heaters[name].level = int(dev["level"])
        self.devices_at = t
        heating = self._heating()
        if heating and not was_heating:
            self.heating_since = t
        elif not heating:
            self.heating_since = None
        # 가상 주방의 자체 차단은 false → true로 바뀔 때만 SAFE_STOP으로 들어간다.
        # safe_stop은 새 명령을 받을 때까지 true로 남으므로, 식어서 풀린 뒤 다시 들어가지 않게.
        if payload["safe_stop"] and not self.kitchen_safe_stop:
            self.safe_stop = "kitchen"
        self.kitchen_safe_stop = bool(payload["safe_stop"])

    def _on_reading(self, t: float, payload: dict[str, Any]) -> None:
        heater = self.heaters.get(payload["device_id"])
        if heater is None:  # 가열 장치가 아닌 센서
            return
        temp = float(payload["temperature_c"])
        heater.temperature_c, heater.temp_at = temp, t
        heater.hot = temp >= DANGER_C or (heater.hot and temp >= DANGER_EXIT_C)

    def _on_vision(self, t: float, payload: dict[str, Any]) -> None:
        if any(o.get("cls") == "person" for o in payload["objects"]):
            self.absent_since = None
        elif self.absent_since is None:
            # 화면이 끊겼다 돌아왔으면 마지막 화면(사람이 보였던 때)부터 없던 것으로 본다
            self.absent_since = self.vision_at if self._vision_gap(t) else t
        self.vision_at = t

    def _release_safe_stop(self, t: float) -> None:
        """가열 장치가 모두 꺼지고, 모두 100°C 아래인 것을 확인하면 SAFE_STOP을 푼다."""
        if self.safe_stop is None or self._heating():
            return
        temps = [self._temp(h, t) for h in self.heaters.values()]
        if all(v is not None and v < COOK_C for v in temps):  # 온도를 모르면 풀지 않는다
            self.safe_stop = None

    # ── 읽기 ──────────────────────────────────────────────────────────

    def _heating(self) -> bool:
        return any(h.on for h in self.heaters.values())

    def _temp(self, heater: _Heater, t: float) -> float | None:
        """믿을 수 있는 온도. 끊겼으면 None."""
        if heater.temp_at is None or t - heater.temp_at > TEMP_STALE_S:
            return None
        return heater.temperature_c

    def _vision_gap(self, t: float) -> bool:
        return self.vision_at is None or t - self.vision_at > VISION_STALE_S

    def person(self, t: float) -> bool | None:
        """사람이 보이는가. 화면이 끊겼으면 None (판정에서는 없음으로 본다)."""
        if self._vision_gap(t):
            return None
        return self.absent_since is None

    def absent_s(self, t: float) -> float:
        """가열 장치가 켜진 채 사람이 없는 시간 (켜진 때부터 센다)."""
        if self.heating_since is None or self.person(t):
            return 0.0
        # 사람이 안 보이기 시작한 때. 보이던 중에 화면이 끊겼으면 마지막 화면 때부터
        since = self.absent_since if self.absent_since is not None else self.vision_at
        return max(0.0, t - max(since, self.heating_since))

    def state(self, t: float) -> str:
        if self.safe_stop is not None:
            return "SAFE_STOP"
        if any(h.hot and self._temp(h, t) is not None for h in self.heaters.values()):
            return "DANGER"
        if not self._heating():
            return "IDLE"
        if self.absent_s(t) >= UNATTENDED_S:
            return "UNATTENDED"
        on_temps = [self._temp(h, t) for h in self.heaters.values() if h.on]
        if any(v is not None and v >= COOK_C for v in on_temps):
            return "COOKING"
        return "PREHEAT"

    def stale(self, t: float) -> list[str]:
        """믿지 않는 근거: `vision`, `devices`, 온도가 끊긴 가열 장치 이름."""
        out = []
        if self._vision_gap(t):
            out.append("vision")
        if self.devices_at is None or t - self.devices_at > DEVICES_STALE_S:
            out.append("devices")
        out += [name for name, h in self.heaters.items() if self._temp(h, t) is None]
        return out

    def risk(self, t: float, state: str | None = None) -> str:
        state = state or self.state(t)
        if state in RISKY:
            return "danger"
        temps = [self._temp(h, t) for h in self.heaters.values()]
        if any(v is not None and v >= WARN_C for v in temps):
            return "warn"
        if self.absent_s(t) >= UNATTENDED_WARN_S:
            return "warn"
        # 켜진 가열 장치의 온도를 모르면 위험한지 알 수 없다
        if any(h.on and self._temp(h, t) is None for h in self.heaters.values()):
            return "warn"
        return "none"

    def evidence(self, t: float) -> dict[str, Any]:
        """`fusion/state`의 `evidence` (interfaces §2.3)."""
        heaters = {}
        for name, h in self.heaters.items():
            temp = self._temp(h, t)
            heaters[name] = {
                "on": h.on,
                "level": h.level,
                "temperature_c": None if temp is None else round(temp, 1),
            }
        return {
            "heaters": heaters,
            "person": self.person(t),
            "absent_s": round(self.absent_s(t), 1),
            "safe_stop": self.safe_stop,
            "stale": self.stale(t),
        }
