"""시나리오 파일(YAML) 읽기와 값 계산.

형식은 services/simulator/README.md 참고.
잘못된 시나리오는 어디가 틀렸는지 알려 주는 ScenarioError를 낸다.
"""

from __future__ import annotations

import bisect
import dataclasses
import pathlib
from typing import Any

import yaml

from common.kitchen_link import HEATERS, TARGET_C
from services.safety_guard.rules import STATES


class ScenarioError(ValueError):
    pass


Points = list[tuple[float, float]]


def _points(raw: Any, field: str) -> Points:
    """[[시각, 값], ...] → 시각 순 정렬된 (float, float) 목록."""
    if not isinstance(raw, list) or not raw:
        raise ScenarioError(f"{field}: [[시각, 값], ...] 목록이어야 합니다")
    try:
        pts = sorted((float(t), float(v)) for t, v in raw)
    except (TypeError, ValueError) as exc:
        raise ScenarioError(f"{field}: 각 항목은 [시각, 숫자] 이어야 합니다 ({exc})") from exc
    return pts


def interpolate(points: Points, t: float) -> float:
    """구간 사이는 선형 보간, 범위 밖은 끝 값 유지."""
    times = [p[0] for p in points]
    if t <= times[0]:
        return points[0][1]
    if t >= times[-1]:
        return points[-1][1]
    i = bisect.bisect_right(times, t)
    (t0, v0), (t1, v1) = points[i - 1], points[i]
    return v0 + (v1 - v0) * (t - t0) / (t1 - t0)


@dataclasses.dataclass(frozen=True)
class SensorStream:
    device_id: str
    hz: float
    temperature_c: Points
    current_a: Points


@dataclasses.dataclass(frozen=True)
class HeaterStream:
    """가열 장치별 세기 시간표. 온도는 가상 온도 규칙으로 계산한다 (runner.heater_readings)."""

    levels: dict[str, list[tuple[float, int]]]  # 장치 → [(시각, 그 시각부터의 세기 0~3)]

    def level_at(self, device: str, t: float) -> int:
        current = 0
        for start, level in self.levels.get(device, []):
            if start <= t:
                current = level
        return current


@dataclasses.dataclass(frozen=True)
class VisionStream:
    fps: float
    objects: list[tuple[float, list[str]]]  # (시각, 그 시각부터 보이는 클래스 목록)

    def visible_at(self, t: float) -> list[str]:
        current: list[str] = []
        for start, classes in self.objects:
            if start <= t:
                current = classes
        return current


@dataclasses.dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    duration_s: float
    heartbeat_hz: float
    sensor: SensorStream | None
    vision: VisionStream | None
    stt: list[tuple[float, str]]
    heaters: HeaterStream | None = None
    expected: list[tuple[float, str]] = dataclasses.field(default_factory=list)  # 정답 State 구간


def _positive(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScenarioError(f"{field}: 숫자여야 합니다") from exc
    if number <= 0:
        raise ScenarioError(f"{field}: 0보다 커야 합니다")
    return number


def parse(raw: dict[str, Any]) -> Scenario:
    if not isinstance(raw, dict):
        raise ScenarioError("시나리오 최상위는 key: value 형식이어야 합니다")
    known = {
        "name",
        "description",
        "duration_s",
        "heartbeat_hz",
        "sensor",
        "heaters",
        "vision",
        "stt",
        "expected",
    }
    unknown = set(raw) - known
    if unknown:
        raise ScenarioError(f"알 수 없는 키: {sorted(unknown)} (사용 가능: {sorted(known)})")
    if "name" not in raw or "duration_s" not in raw:
        raise ScenarioError("name, duration_s는 필수입니다")
    if raw.get("sensor") is not None and raw.get("heaters") is not None:
        raise ScenarioError("sensor와 heaters는 함께 쓸 수 없습니다 (둘 다 sensor/reading을 보냄)")

    sensor = None
    if raw.get("sensor") is not None:
        s = raw["sensor"]
        sensor = SensorStream(
            device_id=str(s.get("device_id", "esp32-sim")),
            hz=_positive(s.get("hz", 1), "sensor.hz"),
            temperature_c=_points(s.get("temperature_c"), "sensor.temperature_c"),
            current_a=_points(s.get("current_a", [[0, 0]]), "sensor.current_a"),
        )

    vision = None
    if raw.get("vision") is not None:
        v = raw["vision"]
        entries = v.get("objects")
        if not isinstance(entries, list) or not entries:
            raise ScenarioError("vision.objects: [[시각, [클래스, ...]], ...] 목록이어야 합니다")
        objects = []
        for entry in entries:
            if not (isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], list)):
                raise ScenarioError(f"vision.objects 항목 형식 오류: {entry!r}")
            objects.append((float(entry[0]), [str(c) for c in entry[1]]))
        vision = VisionStream(fps=_positive(v.get("fps", 2), "vision.fps"), objects=sorted(objects))

    heaters = _heaters(raw["heaters"]) if raw.get("heaters") is not None else None

    stt = []
    for entry in raw.get("stt") or []:
        if not (isinstance(entry, list) and len(entry) == 2):
            raise ScenarioError(f'stt 항목은 [시각, "발화"] 이어야 합니다: {entry!r}')
        stt.append((float(entry[0]), str(entry[1])))

    return Scenario(
        name=str(raw["name"]),
        description=str(raw.get("description", "")),
        duration_s=_positive(raw["duration_s"], "duration_s"),
        heartbeat_hz=_positive(raw.get("heartbeat_hz", 1), "heartbeat_hz"),
        sensor=sensor,
        vision=vision,
        stt=sorted(stt),
        heaters=heaters,
        expected=_expected(raw.get("expected")),
    )


def _heaters(raw: Any) -> HeaterStream:
    if not isinstance(raw, dict) or not raw:
        raise ScenarioError("heaters: {장치: [[시각, 세기], ...]} 형식이어야 합니다")
    levels: dict[str, list[tuple[float, int]]] = {}
    for device, entries in raw.items():
        if device not in HEATERS:
            raise ScenarioError(f"heaters: 가열 장치는 {HEATERS} 중 하나여야 합니다: {device!r}")
        if not isinstance(entries, list) or not entries:
            raise ScenarioError(f"heaters.{device}: [[시각, 세기], ...] 목록이어야 합니다")
        timeline = []
        for entry in entries:
            ok = isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], int)
            if not ok or isinstance(entry[1], bool) or entry[1] not in TARGET_C:
                message = f"heaters.{device}: 항목은 [시각, 세기 0~3]이어야 합니다: {entry!r}"
                raise ScenarioError(message)
            timeline.append((float(entry[0]), entry[1]))
        levels[device] = sorted(timeline)
    return HeaterStream(levels=levels)


def _expected(raw: Any) -> list[tuple[float, str]]:
    """정답 State 구간 [[시각, State], ...] — 0초부터 시작, 시각이 늘어나야 한다."""
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise ScenarioError("expected: [[시각, State], ...] 목록이어야 합니다")
    labels: list[tuple[float, str]] = []
    for entry in raw:
        if not (isinstance(entry, list) and len(entry) == 2) or entry[1] not in STATES:
            states = "|".join(STATES)
            raise ScenarioError(f"expected: 항목은 [시각, {states}]이어야 합니다: {entry!r}")
        labels.append((float(entry[0]), entry[1]))
    times = [t for t, _ in labels]
    if times[0] != 0 or any(b <= a for a, b in zip(times, times[1:], strict=False)):
        raise ScenarioError("expected: 0초부터 시작하고 시각이 늘어나야 합니다")
    return labels


def expected_at(sc: Scenario, t: float) -> str | None:
    """시각 t의 정답 State (정답이 없는 시나리오면 None)."""
    current = None
    for start, state in sc.expected:
        if start <= t:
            current = state
    return current


def load(path: str | pathlib.Path) -> Scenario:
    path = pathlib.Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioError(f"{path.name}: YAML 문법 오류 — {exc}") from exc
    try:
        return parse(raw)
    except ScenarioError as exc:
        raise ScenarioError(f"{path.name}: {exc}") from exc
