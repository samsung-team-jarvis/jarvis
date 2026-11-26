import json
import threading
import urllib.error
import urllib.request

import pytest

from common.bus import MemoryBus
from common.messages import Envelope
from services.safety_guard.service import FAST_PATH_REASON, STATE_STALE_S
from services.webview.server import Server
from services.webview.service import TURN_S, Feed, device_label


class Rig:
    def __init__(self) -> None:
        self.now = 100.0
        self.bus = MemoryBus()
        self.feed = Feed(self.bus, "s_web", device="테스트", clock=lambda: self.now)
        self.feed.start()

    def send(self, topic: str, payload: dict, mono: float | None = None) -> None:
        msg = Envelope.new(topic, "test", payload, "s_in")
        if mono is not None:
            msg = Envelope(**{**msg.__dict__, "mono": mono})
        self.bus.publish(msg)

    def speech(self, text: str, wake: bool = True, end: float = 10.0, at: float = 10.5) -> None:
        payload = {"text": text, "wake": wake, "audio_ms": 2000, "stt_ms": 120}
        self.send("stt/text", {**payload, "speech_end_mono": end}, mono=at)

    def call(self, raw: str, call: dict) -> None:
        payload = {"call": call, "raw_text": raw, "valid": True, "fallback": False}
        self.send("llm/function_call", {**payload, "gen_ms": 800.0, "tokens": 9})

    def decision(self, call: dict, decision: str = "ALLOW", reason: str = "") -> None:
        self.send("guard/decision", {"call": call, "decision": decision, "reason": reason})

    def result(self, at: float = 11.5) -> None:
        payload = {"seq": 1, "ok": True, "retries": 0, "rtt_ms": 2.2}
        self.send("control/result", payload, mono=at)

    def state(self, state: str = "COOKING", risk: str = "none", **evidence) -> None:
        ev = {"heaters": {}, "person": True, "absent_s": 0.0, "safe_stop": None, "stale": []}
        ev.update(evidence)
        payload = {"state": state, "prev_state": state, "evidence": ev, "risk": risk}
        self.send("fusion/state", payload)

    @property
    def view(self) -> dict:
        return self.feed.snapshot()


HOOD_ON = {"action": "TURN_ON", "target": "hood"}


def test_voice_turn_collects_each_step_and_latency() -> None:
    rig = Rig()
    rig.speech("자비스 후드 켜줘.")
    rig.call("<jarvis_1>(target=hood)<jarvis_end>", HOOD_ON)
    rig.decision(HOOD_ON)
    rig.result(at=11.5)
    t = rig.view["turn"]
    assert (t["kind"], t["said"], t["command"]) == ("voice", "자비스 후드 켜줘.", "후드 켜줘.")
    assert t["raw_text"] == "<jarvis_1>(target=hood)<jarvis_end>"
    assert (t["decision"], t["reply"]) == ("ALLOW", "후드를 켰습니다.")
    assert (t["publish_ms"], t["gen_ms"], t["rtt_ms"], t["e2e_ms"]) == (500.0, 800.0, 2.2, 1500.0)
    assert rig.view["log"][-1]["reply"] == "후드를 켰습니다."


def test_speech_without_wake_word_is_not_shown() -> None:
    rig = Rig()
    rig.speech("오늘 손님 많네", wake=False)
    assert rig.view["turn"] is None


def test_fast_path_skips_llm_and_ignores_late_llm_result() -> None:
    rig = Rig()
    rig.speech("멈춰.", wake=False)
    stop = {"action": "EMERGENCY_STOP", "target": "all"}
    rig.decision(stop, reason=FAST_PATH_REASON)
    rig.call("<jarvis_8>()<jarvis_end>", stop)
    t = rig.view["turn"]
    assert t["kind"] == "fast" and "raw_text" not in t
    assert t["reply"].startswith("긴급 정지")


def test_auto_stop_is_its_own_turn() -> None:
    rig = Rig()
    rig.speech("자비스 1번 화구 켜줘.")
    off = {"action": "TURN_OFF", "target": "burner_1"}
    rig.decision(off, reason="자동 차단: 방치 (사람 없음 60초)")
    t = rig.view["turn"]
    assert (t["kind"], t["command"]) == ("auto", None)
    assert t["reason"].startswith("자동 차단")


def test_reply_to_question_without_wake_word() -> None:
    rig = Rig()
    pay = {"action": "REQUEST_PAYMENT"}
    rig.speech("자비스 결제해줘.")
    rig.call("<jarvis_12>()<jarvis_end>", pay)
    rig.decision(pay, "ASK", "결제는 확인을 받은 뒤 실행해요.")
    assert rig.view["turn"]["reply"] == "결제할까요?"
    rig.speech("네.", wake=False)
    assert rig.view["turn"]["kind"] == "reply"


def test_old_turn_does_not_take_new_results() -> None:
    rig = Rig()
    rig.speech("자비스 후드 켜줘.")
    rig.now += TURN_S + 1
    rig.decision(HOOD_ON)
    assert rig.view["turn"]["kind"] == "other"  # 판정만 따로 온 것 (예: 시뮬레이터)


def test_state_devices_warning_and_stale() -> None:
    rig = Rig()
    assert rig.view["stale"] and rig.view["state_text"] == "상태 모름"
    heaters = {"burner_1": {"on": True, "level": 3, "temperature_c": 210.0}}
    rig.state("COOKING", "warn", heaters=heaters)
    devices = {"burner_1": {"on": True, "level": 3}}
    rig.send("device/state", {"devices": devices, "safe_stop": False})
    v = rig.view
    assert (v["state_text"], v["risk"], v["stale"]) == ("조리 중", "warn", False)
    assert v["heaters"]["burner_1"]["temperature_c"] == 210.0
    assert v["devices"]["burner_1"] == {"on": True, "level": 3}
    assert v["warning"].startswith("주의하세요")
    rig.now += STATE_STALE_S + 0.1
    assert rig.view["stale"] and rig.view["heaters"] == {}


def test_device_label_says_when_not_on_board() -> None:
    assert Rig().view["device"] == "테스트"
    label = device_label()
    assert "오프라인" in label or "참고값" in label


def test_alive_services_from_heartbeats() -> None:
    rig = Rig()
    rig.bus.publish(Envelope.new("system/heartbeat", "llm_svc", {"alive": True}, "s"))
    assert rig.view["alive"] == ["llm_svc"]
    rig.now += 5
    assert rig.view["alive"] == []


def test_reset_clears_turn_and_log_but_keeps_devices() -> None:
    rig = Rig()
    rig.send("device/state", {"devices": {"hood": {"on": True, "level": 1}}, "safe_stop": False})
    rig.speech("자비스 후드 켜 줘.")
    rig.decision({"action": "TURN_ON", "target": "hood"})
    assert rig.view["turn"] and rig.view["log"]
    before = rig.view["version"]
    rig.feed.reset()
    v = rig.view
    assert v["turn"] is None and v["log"] == [] and v["mic"] is None
    assert v["devices"]["hood"]["on"]  # 장치 상태는 그대로
    assert v["version"] > before  # 화면이 바로 다시 그려진다


@pytest.mark.parametrize("kind", ["mic", "speaker"])
def test_request_test_publishes_audio_test(kind: str) -> None:
    rig = Rig()
    sent: list[dict] = []
    rig.bus.subscribe("audio/test", lambda m: sent.append(m.payload))
    rig.feed.request_test(kind)
    assert sent == [{"kind": kind}]
    v = rig.view
    if kind == "mic":
        assert v["mic"]["waiting"] and v["speaker_age_s"] is None
    else:
        assert v["speaker_age_s"] == 0.0 and v["mic"] is None


def test_request_test_rejects_other_kinds() -> None:
    with pytest.raises(ValueError):
        Rig().feed.request_test("hood")


def test_mic_level_shows_whether_sound_came_in() -> None:
    rig = Rig()
    rig.feed.request_test("mic")
    rig.send("audio/level", {"dbfs": -20.0, "peak_dbfs": -20.0, "remaining_s": 3.0})
    assert rig.view["mic"] == {
        "dbfs": -20.0,
        "peak_dbfs": -20.0,
        "remaining_s": 3.0,
        "heard": True,
        "waiting": False,
    }
    rig.send("audio/level", {"dbfs": -55.0, "peak_dbfs": -48.0, "remaining_s": 0.0})
    assert rig.view["mic"]["heard"] is False  # 잡음뿐 (보드 USB 동글 마이크 -38~-60 dBFS)


def test_http_buttons() -> None:
    rig = Rig()
    sent: list[dict] = []
    rig.bus.subscribe("audio/test", lambda m: sent.append(m.payload))
    rig.speech("자비스 후드 켜 줘.")
    server = Server(("127.0.0.1", 0), rig.feed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str) -> int:
        req = urllib.request.Request(base + path, data=b"", method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    try:
        assert post("/test/mic") == 200 and post("/test/speaker") == 200
        assert sent == [{"kind": "mic"}, {"kind": "speaker"}]
        assert post("/reset") == 200 and rig.view["turn"] is None
        assert post("/test/hood") == 404 and post("/nothing") == 404
    finally:
        server.stop()


def test_http_page_json_and_events() -> None:
    rig = Rig()
    rig.state()
    server = Server(("127.0.0.1", 0), rig.feed)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as r:
            assert "자비스" in r.read().decode()
        with urllib.request.urlopen(base + "/view.json", timeout=5) as r:
            assert json.load(r)["state"] == "COOKING"
        with urllib.request.urlopen(base + "/events", timeout=5) as r:
            first = r.readline().decode()
            assert first.startswith("data: ") and json.loads(first[6:])["state"] == "COOKING"
    finally:
        server.stop()
