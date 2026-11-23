import pytest

from services.audio_svc.__main__ import followup_kind


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"call": {"action": "ASK_CLARIFY"}, "decision": "ALLOW"}, True),  # 되묻기 → 합침
        ({"call": {"action": "TURN_ON", "target": "hood"}, "decision": "ALLOW"}, False),
        ({"call": {"action": "CHECK_STATUS"}, "decision": "ALLOW"}, False),
        ({"call": {"action": "TURN_ON", "target": "burner_1"}, "decision": "REJECT"}, None),
        (
            {"call": {"action": "REQUEST_PAYMENT"}, "decision": "ASK"},
            None,
        ),  # Guard가 네/아니요를 받는다
        ({"call": {"action": "UNSUPPORTED"}, "decision": "ALLOW"}, None),  # 잡담이 이어지지 않게
        ({"call": {"action": "EMERGENCY_STOP", "target": "all"}, "decision": "ALLOW"}, None),
        (
            {
                "call": {"action": "TURN_OFF", "target": "burner_1"},
                "decision": "ALLOW",
                "reason": "자동 차단: 방치 (사람 없음 60초)",
            },
            None,
        ),
    ],
)
def test_followup_kind(payload: dict, expected: bool | None) -> None:
    assert followup_kind(payload) is expected
