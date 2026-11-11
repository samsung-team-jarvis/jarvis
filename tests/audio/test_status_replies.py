"""상태·위험 확인 응답, 자동 차단 이유, State별 위험 경고 (STT-13)."""

from services.audio_svc.responses import (
    NO_STATUS,
    STALE_STATUS,
    KitchenStatus,
    RiskWatcher,
    reply_for_decision,
)


def heaters(**on: tuple[int, float | None]) -> dict:
    """켜진 가열 장치만 (세기, 온도). 나머지는 꺼짐·25°C."""
    out = {
        n: {"on": False, "level": 0, "temperature_c": 25.0}
        for n in ("burner_1", "burner_2", "fryer")
    }
    for name, (level, temp) in on.items():
        out[name] = {"on": True, "level": level, "temperature_c": temp}
    return out


def fusion(state: str, risk: str = "none", absent_s: float = 0.0, safe_stop=None, **on) -> dict:
    hs = heaters(**on)
    return {
        "state": state,
        "prev_state": state,
        "risk": risk,
        "evidence": {
            "heaters": hs,
            "person": True,
            "absent_s": absent_s,
            "safe_stop": safe_stop,
            "stale": [],
        },
    }


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def status_with(payload: dict, devices: dict | None = None) -> tuple[KitchenStatus, Clock]:
    clock = Clock()
    st = KitchenStatus(clock=clock)
    st.on_state(payload)
    if devices is not None:
        st.on_devices({"devices": devices, "safe_stop": False})
    return st, clock


def ask(st: KitchenStatus | None, call: dict) -> str | None:
    return reply_for_decision({"call": call, "decision": "ALLOW", "reason": ""}, st)


def test_check_status_lists_state_and_devices_that_are_on() -> None:
    st, _ = status_with(
        fusion("COOKING", burner_1=(3, 182.4)),
        devices={"hood": {"on": True, "level": 2}, "light": {"on": True, "level": 3}},
    )
    assert ask(st, {"action": "CHECK_STATUS"}) == (
        "지금은 조리 중이에요. 켜진 장치는 1번 화구 강 182도, 후드 중, 조명 켜짐이에요."
    )


def test_check_status_when_everything_is_off() -> None:
    st, _ = status_with(fusion("IDLE"), devices={"hood": {"on": False, "level": 0}})
    assert ask(st, {"action": "CHECK_STATUS"}) == "지금은 켜진 장치가 없어요."


def test_check_status_of_one_device() -> None:
    st, _ = status_with(
        fusion("PREHEAT", burner_2=(1, 60.0)) | {},
        devices={"hood": {"on": True, "level": 3}, "music": {"on": True, "level": 1}},
    )
    st.state["evidence"]["heaters"]["burner_1"]["temperature_c"] = 150.0  # 꺼졌지만 아직 뜨거움
    assert ask(st, {"action": "CHECK_STATUS", "target": "burner_2"}) == (
        "2번 화구는 켜져 있어요. 세기 약, 60도예요."
    )
    assert ask(st, {"action": "CHECK_STATUS", "target": "burner_1"}) == (
        "1번 화구는 꺼져 있어요. 아직 150도라 뜨거워요."
    )
    assert (
        ask(st, {"action": "CHECK_STATUS", "target": "hood"})
        == "후드는 켜져 있어요. 세기 강이에요."
    )
    assert ask(st, {"action": "CHECK_STATUS", "target": "music"}) == "음악은 켜져 있어요."
    assert (
        ask(st, {"action": "CHECK_STATUS", "target": "fan"}) == "선풍기 상태를 아직 받지 못했어요."
    )


def test_unknown_temperature_is_said_not_guessed() -> None:
    st, _ = status_with(fusion("PREHEAT", "warn", fryer=(2, None)))
    assert ask(st, {"action": "CHECK_STATUS", "target": "fryer"}) == (
        "튀김기는 켜져 있어요. 세기 중, 온도는 알 수 없어요."
    )
    assert ask(st, {"action": "CHECK_RISK"}) == "주의가 필요해요. 튀김기 온도를 알 수 없어요."


def test_check_risk_gives_reasons() -> None:
    st, _ = status_with(fusion("COOKING"))
    assert ask(st, {"action": "CHECK_RISK"}) == "지금은 위험하지 않아요."
    st.on_state(fusion("DANGER", "danger", burner_1=(3, 245.0)))
    assert ask(st, {"action": "CHECK_RISK"}) == "위험해요. 1번 화구가 245도로 너무 뜨거워요."
    st.on_state(fusion("COOKING", "warn", absent_s=14.2, burner_2=(2, 205.0)))
    assert ask(st, {"action": "CHECK_RISK"}) == (
        "주의가 필요해요. 2번 화구가 205도예요. 사람 없이 14초째 켜져 있어요."
    )


def test_no_or_old_state_is_not_reported_as_safe() -> None:
    assert ask(None, {"action": "CHECK_RISK"}) == NO_STATUS
    assert ask(KitchenStatus(), {"action": "CHECK_STATUS"}) == NO_STATUS
    st, clock = status_with(fusion("IDLE"))
    clock.t += 6  # fusion/state가 5초 넘게 안 옴 (fusion_svc가 멈춤 등)
    assert ask(st, {"action": "CHECK_RISK"}) == STALE_STATUS
    assert ask(st, {"action": "CHECK_STATUS"}) == STALE_STATUS


def test_auto_stop_says_why() -> None:
    def auto(target: str, reason: str) -> str | None:
        call = {"action": "TURN_OFF", "target": target}
        return reply_for_decision({"call": call, "decision": "ALLOW", "reason": reason})

    assert (
        auto("burner_1", "자동 차단: 과열 (1번 화구 241°C)")
        == "온도가 너무 높아 1번 화구를 껐습니다."
    )
    assert (
        auto("fryer", "자동 차단: 방치 (사람 없음 61초)")
        == "자리를 오래 비우셔서 튀김기를 껐습니다."
    )
    # 사람이 한 명령은 그대로
    assert (
        reply_for_decision(
            {
                "call": {"action": "TURN_OFF", "target": "burner_1"},
                "decision": "ALLOW",
                "reason": "",
            }
        )
        == "1번 화구를 껐습니다."
    )


def test_risk_warning_names_the_danger() -> None:
    w = RiskWatcher()
    said = [
        w.update(fusion("COOKING", burner_1=(3, 150.0))),
        w.update(fusion("COOKING", "warn", burner_1=(3, 210.0))),
        w.update(fusion("COOKING", "warn", burner_1=(3, 220.0))),  # 같은 위험 — 말하지 않음
        w.update(fusion("DANGER", "danger", burner_1=(3, 241.0))),
        w.update(fusion("DANGER", "danger", burner_1=(0, 238.0))),
        w.update(
            fusion("UNATTENDED", "danger", absent_s=31, burner_2=(1, 120.0))
        ),  # 위험 종류 바뀜
        w.update(fusion("COOKING", burner_2=(1, 120.0))),
    ]
    assert said == [
        None,
        "주의하세요. 1번 화구가 210도예요.",
        None,
        "위험해요. 1번 화구가 241도로 너무 뜨거워요.",
        None,
        "가열 장치가 켜진 채 자리를 비우셨어요. 30초 안에 돌아오지 않으면 불을 끕니다.",
        None,
    ]
