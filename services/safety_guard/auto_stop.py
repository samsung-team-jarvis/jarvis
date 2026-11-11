"""자동 차단 (FUS-09): `fusion/state`의 근거 → 꺼야 할 가열 장치.

결정: docs/decisions/2026-11-11-auto-stop.md.
사람·LLM을 기다리지 않는다 (위험 감지는 LLM을 거치지 않는다).

| 위험 | 언제 | 무엇을 |
|---|---|---|
| 과열 | 켜진 가열 장치가 240°C 이상이면 바로 | 그 장치만 |
| 방치 | 켜진 채 사람이 60초 없으면 (방치 30초 + 경고 뒤 유예 30초) | 켜진 가열 장치 |

방치는 사람이 보이면 처음부터 다시 센다.

후드·조명 등은 끄지 않는다 (연기를 빼야 한다). 끄라고 보낸 장치가 RESEND_S 뒤에도 켜져 있으면
(확인 실패·가상 주방이 늦게 받음) 다시 보낸다. 장치가 켜져 있는지·온도·사람 없는 시간은
`fusion/state`의 `evidence`를 그대로 쓴다 (interfaces §2.3).
"""

from __future__ import annotations

from typing import Any

from common.kitchen_link import HEATERS
from services.fusion_svc.state_machine import DANGER_C, UNATTENDED_S

UNATTENDED_GRACE_S = 30.0  # UNATTENDED(음성 경고) 뒤 사람이 돌아올 시간
STOP_ABSENT_S = UNATTENDED_S + UNATTENDED_GRACE_S
RESEND_S = 3.0  # 끄라고 보낸 뒤 이 시간이 지나도 켜져 있으면 다시 보낸다

REASON_PREFIX = "자동 차단"
DEVICE_NAMES = {"burner_1": "1번 화구", "burner_2": "2번 화구", "fryer": "튀김기"}


class AutoStop:
    def __init__(self) -> None:
        self.sent: dict[str, float] = {}  # 장치 → 마지막으로 끄라고 보낸 시각

    def check(self, payload: dict[str, Any], now: float) -> list[tuple[str, str]]:
        """끌 장치와 이유 [(장치, reason)]. 같은 장치는 RESEND_S 안에 다시 내지 않는다."""
        evidence = payload.get("evidence") or {}
        heaters = evidence.get("heaters") or {}
        absent_s = evidence.get("absent_s") or 0.0
        out: list[tuple[str, str]] = []
        for name in HEATERS:
            heater = heaters.get(name) or {}
            if not heater.get("on"):
                self.sent.pop(name, None)  # 꺼졌다 — 다음에 다시 켜지면 처음부터
                continue
            temp = heater.get("temperature_c")
            if temp is not None and temp >= DANGER_C:
                reason = f"{REASON_PREFIX}: 과열 ({DEVICE_NAMES[name]} {temp:.0f}°C)"
            elif absent_s >= STOP_ABSENT_S:
                reason = f"{REASON_PREFIX}: 방치 (사람 없음 {absent_s:.0f}초)"
            else:
                continue
            last = self.sent.get(name)
            if last is not None and now - last < RESEND_S:
                continue
            self.sent[name] = now
            out.append((name, reason))
        return out
