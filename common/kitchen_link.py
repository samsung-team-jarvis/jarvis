"""보드 ↔ 가상 주방 연결 메시지 (interfaces.md §4, HW-14).

가상 주방(Unity)은 버스의 봉투 메시지를 직접 쓰지 않는다. 봉투 없는 짧은 JSON을 `kitchen/*` 토픽으로
주고받고, 보드의 `kitchen_gw`가 버스 메시지로 옮기면서 보드 시계로 시각을 찍는다
(시각은 보드 한 대의 시계만 쓴다 — overview §5).

이 파일과 문서가 다르면 문서를 먼저 고친다. Unity 쪽 C# 코드도 여기의 상수와 규칙을 따른다.
"""

from __future__ import annotations

import json
import math
from typing import Any

from common.function_call import DEVICES, LEVELS, TARGETS

TOPIC_CMD = "kitchen/cmd"  # 보드 → 가상 주방: 장치 제어 명령
TOPIC_ACK = "kitchen/ack"  # 가상 주방 → 보드: 명령 결과 확인
TOPIC_TEMP = "kitchen/temp"  # 가상 주방 → 보드: 가열 장치 온도 (1Hz)
TOPIC_FRAME = "kitchen/frame"  # 가상 주방 → 보드: 인식용 카메라 화면 (JPEG 바이트, 봉투·JSON 아님)
TOPIC_HEARTBEAT = "kitchen/heartbeat"  # 보드 → 가상 주방: 생존 신호
TOPIC_STATE = "kitchen/state"  # 가상 주방 → 보드: 장치 상태

CMDS = ("ON", "OFF", "LEVEL")
HEATERS = ("burner_1", "burner_2")  # 온도를 가진 가열 장치 (v0.2에서 튀김기 추가)

ACK_TIMEOUT_S = 0.5  # 이 안에 확인이 없으면 다시 보낸다
MAX_RETRIES = 1  # 다시 보내는 횟수
HEARTBEAT_PERIOD_S = 1.0
HEARTBEAT_TIMEOUT_S = 3.0  # 이만큼 생존 신호가 없으면 가상 주방이 가열 장치를 끈다 (L0)

FRAME_WIDTH, FRAME_HEIGHT, FRAME_FPS = 640, 360, 4

# 가상 온도 규칙 — 시연용 설계값이다 (실제 조리 온도를 잰 값이 아님)
TEMP_PERIOD_S = 1.0
TEMP_RATE = 0.05  # 1초마다 목표 온도와의 차이 중 이만큼 다가간다
TARGET_C = {0: 25.0, 1: 120.0, 2: 180.0, 3: 270.0}  # 세기 → 목표 온도 (0 = 꺼짐, 실온)
HARD_LIMIT_C = 265.0  # 이 온도에 닿으면 가상 주방이 스스로 그 가열 장치를 끈다 (L0)


class LinkError(ValueError):
    """연결 메시지가 규격에 맞지 않을 때."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_command(payload: dict[str, Any]) -> None:
    """`control/command`·`kitchen/cmd` payload `{seq, cmd, target, value}`를 검사한다."""
    seq, cmd, target, value = (payload.get(k) for k in ("seq", "cmd", "target", "value"))
    if not _is_int(seq) or seq < 0:
        raise LinkError(f"seq는 0 이상의 정수여야 합니다: {seq!r}")
    if cmd not in CMDS:
        raise LinkError(f"cmd는 {CMDS} 중 하나여야 합니다: {cmd!r}")
    if target not in TARGETS:
        raise LinkError(f"target은 {TARGETS} 중 하나여야 합니다: {target!r}")
    if cmd != "OFF" and target not in DEVICES:
        raise LinkError(f"{cmd}에는 all을 쓸 수 없습니다 (전체는 끄기만)")
    expected = {"ON": (1,), "OFF": (0,), "LEVEL": LEVELS}[cmd]
    if not _is_int(value) or value not in expected:
        raise LinkError(f"{cmd}의 value는 {expected} 중 하나여야 합니다: {value!r}")


def command_for(call: dict[str, Any], seq: int) -> dict[str, Any] | None:
    """허용된 Function Call(interfaces §3) → 장치 제어 명령. 장치를 바꾸지 않는 Action이면 None.

    타이머는 보드가 세고, 끝났을 때 TURN_OFF로 이 함수를 다시 부른다.
    """
    action = call["action"]
    if action == "TURN_ON":
        command = {"seq": seq, "cmd": "ON", "target": call["target"], "value": 1}
    elif action == "TURN_OFF":
        command = {"seq": seq, "cmd": "OFF", "target": call["target"], "value": 0}
    elif action == "SET_LEVEL":
        command = {"seq": seq, "cmd": "LEVEL", "target": call["target"], "value": call["level"]}
    elif action == "EMERGENCY_STOP":
        command = {"seq": seq, "cmd": "OFF", "target": "all", "value": 0}
    else:
        return None
    validate_command(command)
    return command


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _decode(data: str | bytes, topic: str) -> dict[str, Any]:
    try:
        raw = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise LinkError(f"{topic}: JSON이 아닙니다: {exc}") from exc
    if not isinstance(raw, dict):
        raise LinkError(f"{topic}: JSON 객체가 아닙니다")
    return raw


def decode_command(data: str | bytes) -> dict[str, Any]:
    payload = _decode(data, TOPIC_CMD)
    validate_command(payload)
    return payload


def decode_ack(data: str | bytes) -> dict[str, Any]:
    """`kitchen/ack` `{seq, ok, reason?}`. `ok=false`면 가상 주방이 명령을 실행하지 않은 것이다."""
    payload = _decode(data, TOPIC_ACK)
    if not _is_int(payload.get("seq")) or not isinstance(payload.get("ok"), bool):
        raise LinkError(f"{TOPIC_ACK}: seq(정수)·ok(true/false)가 필요합니다: {payload!r}")
    return payload


def decode_temp(data: str | bytes) -> dict[str, Any]:
    """`kitchen/temp` `{device_id, temperature_c}`."""
    payload = _decode(data, TOPIC_TEMP)
    device, temp = payload.get("device_id"), payload.get("temperature_c")
    if not isinstance(device, str) or not device:
        raise LinkError(f"{TOPIC_TEMP}: device_id가 비어 있습니다")
    if isinstance(temp, bool) or not isinstance(temp, (int, float)) or not math.isfinite(temp):
        raise LinkError(f"{TOPIC_TEMP}: temperature_c가 숫자가 아닙니다: {temp!r}")
    return payload


def decode_state(data: str | bytes) -> dict[str, Any]:
    """`kitchen/state` `{devices: {이름: {on, level}}, safe_stop}`."""
    payload = _decode(data, TOPIC_STATE)
    devices = payload.get("devices")
    if not isinstance(devices, dict) or not isinstance(payload.get("safe_stop"), bool):
        raise LinkError(f"{TOPIC_STATE}: devices(객체)·safe_stop(true/false)가 필요합니다")
    for name, state in devices.items():
        if (
            not isinstance(state, dict)
            or not isinstance(state.get("on"), bool)
            or not _is_int(state.get("level"))
        ):
            raise LinkError(f"{TOPIC_STATE}: {name}에 on(true/false)·level(정수)이 필요합니다")
    return payload


def next_temperature(current_c: float, level: int, dt_s: float = TEMP_PERIOD_S) -> float:
    """가상 온도 규칙 한 걸음: `dt_s`초 뒤의 온도. `level` 0은 꺼짐.

    1초마다 목표 온도와의 차이의 5%씩 다가간다 (가상 주방과 가짜 가상 주방이 같은 규칙을 쓴다).
    """
    if level not in TARGET_C:
        raise LinkError(f"level은 {tuple(TARGET_C)} 중 하나여야 합니다: {level!r}")
    step = 1.0 - (1.0 - TEMP_RATE) ** (dt_s / TEMP_PERIOD_S)
    return current_c + (TARGET_C[level] - current_c) * step
