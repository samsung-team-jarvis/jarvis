import json

from common import kitchen_link as link
from common.bus import MemoryBus
from common.messages import Envelope
from services.audio_svc.responses import NO_STATUS, STALE_STATUS
from services.dashboard.service import HOLD_S, PERIOD_S, SEEN_S, STATE_STALE_S, Overlay


class Rig:
    def __init__(self) -> None:
        self.now = 100.0
        self.bus = MemoryBus()
        self.sent: list[dict] = []
        self.bus.subscribe_raw(link.TOPIC_OVERLAY, lambda _t, d: self.sent.append(json.loads(d)))
        self.overlay = Overlay(self.bus, "s_dash", clock=lambda: self.now)
        self.overlay.start()

    def send(self, topic: str, payload: dict) -> None:
        self.bus.publish(Envelope.new(topic, "test", payload, "s_in"))

    def state(self, state: str = "COOKING", risk: str = "none", **evidence) -> None:
        heaters = {h: {"on": False, "level": 0, "temperature_c": 25.0} for h in link.HEATERS}
        heaters["burner_1"] = {"on": True, "level": 2, "temperature_c": evidence.pop("temp", 150.0)}
        ev = {"heaters": heaters, "person": True, "absent_s": 0.0, "safe_stop": None, "stale": []}
        ev.update(evidence)
        payload = {"state": state, "prev_state": state, "evidence": ev, "risk": risk}
        self.send("fusion/state", payload)

    def wait(self, seconds: float) -> None:
        self.now += seconds
        self.overlay.tick()

    @property
    def last(self) -> dict:
        return self.sent[-1]


def test_shows_state_and_heaters_from_fusion_state() -> None:
    rig = Rig()
    rig.state("COOKING")
    o = rig.last
    assert (o["state"], o["state_text"], o["risk"], o["stale"]) == (
        "COOKING",
        "조리 중",
        "none",
        False,
    )
    assert o["heaters"]["burner_1"] == {"on": True, "level": 2, "temperature_c": 150.0}
    assert o["person"] is True and o["warning"] is None


def test_heard_and_reply_are_held_for_a_while() -> None:
    rig = Rig()
    rig.state()
    rig.send(
        "stt/text",
        {
            "text": "자비스 후드 켜 줘",
            "wake": True,
            "audio_ms": 0,
            "stt_ms": 0,
            "speech_end_mono": 0,
        },
    )
    rig.send(
        "stt/text",
        {"text": "오늘 손님 많네", "wake": False, "audio_ms": 0, "stt_ms": 0, "speech_end_mono": 0},
    )
    call = {"action": "TURN_ON", "target": "hood"}
    rig.send("guard/decision", {"call": call, "decision": "ALLOW", "reason": ""})
    o = rig.last
    assert o["heard"] == "자비스 후드 켜 줘"  # 호출어 없는 말은 띄우지 않는다
    assert (o["reply"], o["decision"], o["reason"]) == ("후드를 켰습니다.", "ALLOW", None)

    rig.state()
    rig.wait(HOLD_S + 0.1)
    rig.state()
    assert rig.last["heard"] is None and rig.last["reply"] is None


def test_rejection_reason_and_auto_stop_basis_are_shown() -> None:
    rig = Rig()
    rig.state("DANGER", "danger", temp=245.0)
    call = {"action": "TURN_OFF", "target": "burner_1"}
    reason = "자동 차단: 과열 (1번 화구 245°C)"
    rig.send("guard/decision", {"call": call, "decision": "ALLOW", "reason": reason})
    o = rig.last
    assert o["reply"] == "온도가 너무 높아 1번 화구를 껐습니다." and o["reason"] == reason
    assert o["warning"].startswith("위험해요.")  # 음성 경고와 같은 문장


def test_unattended_warning_says_when_it_will_turn_off() -> None:
    rig = Rig()
    rig.state("UNATTENDED", "danger", person=False, absent_s=31.0)
    assert "30초 안에 돌아오지 않으면" in rig.last["warning"]


def test_stale_or_missing_state_is_shown_as_unknown() -> None:
    rig = Rig()
    rig.overlay.tick()
    assert rig.last["state_text"] == "상태 모름" and rig.last["warning"] == NO_STATUS
    rig.state("COOKING")
    rig.wait(STATE_STALE_S + 0.1)
    o = rig.last
    assert (o["state"], o["stale"], o["warning"]) == (None, True, STALE_STATUS)
    assert o["heaters"] == {}  # 끊긴 근거를 계속 보여 주지 않는다


def test_seen_objects_expire() -> None:
    rig = Rig()
    obj = {"cls": "person", "conf": 0.9, "bbox": [1.0, 2.0, 3.0, 4.0]}
    frame = {"objects": [obj], "frame_id": 1, "pre_ms": 0, "npu_ms": 0, "post_ms": 0}
    rig.send("vision/objects", frame)
    rig.overlay.tick()
    assert rig.last["seen"] == [obj]
    rig.wait(SEEN_S + 0.1)
    assert rig.last["seen"] == []


def test_sent_on_change_and_every_second() -> None:
    rig = Rig()
    rig.state()
    count = len(rig.sent)
    rig.wait(PERIOD_S / 2)
    assert len(rig.sent) == count  # 바뀐 게 없으면 1초까지 기다린다
    rig.wait(PERIOD_S / 2)
    assert len(rig.sent) == count + 1
    rig.state("PREHEAT")
    assert len(rig.sent) == count + 2  # 바뀌면 바로


def test_check_status_reply_reads_kitchen_status() -> None:
    rig = Rig()
    rig.state("COOKING")
    rig.send(
        "guard/decision", {"call": {"action": "CHECK_RISK"}, "decision": "ALLOW", "reason": ""}
    )
    assert rig.last["reply"] and "준비 중" not in rig.last["reply"]
