# kitchen_gw — 보드 ↔ 가상 주방 연결

버스의 봉투 메시지와 가상 주방의 연결 토픽(`kitchen/*`) 사이에서 메시지를 옮긴다 (PLAN HW-17). 가상 주방(Unity)은 봉투를 모르고, 이 서비스가 받은 순간에 **보드 시계로** 시각을 찍어 버스에 올린다 ([interfaces](../../docs/architecture/interfaces.md) §4, [decision](../../docs/decisions/2026-10-06-kitchen-link.md)).

```text
control/command ─▶ kitchen/cmd          확인이 0.5초 안에 없으면 같은 seq로 한 번 다시
kitchen/ack     ─▶ control/result       {seq, ok, retries, rtt_ms, reason?}
kitchen/temp    ─▶ sensor/reading       {device_id, temperature_c}
1초마다         ─▶ kitchen/heartbeat    끊기면 가상 주방이 가열 장치를 끈다 (안전 계층 L0)
```

## 실행

```bash
python -m services.kitchen_gw                       # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.kitchen_gw.fake_kitchen          # Unity가 없을 때: 같은 토픽에 답하는 가짜 가상 주방
python -m services.kitchen_gw send ON hood          # 개발용: control/command 하나를 올리고 결과를 본다
python -m services.kitchen_gw send LEVEL burner_1 3
python -m services.kitchen_gw send OFF all
```

Unity 없이 보드 쪽을 개발할 때는 브로커 → 가짜 가상 주방 → `kitchen_gw` 순으로 띄운다 (브로커: [local-development](../../docs/workflows/local-development.md)). `scripts/launch.py`는 `kitchen_gw`를 함께 띄운다. 가짜 가상 주방은 따로 띄운다.

## 동작

| 상황 | 결과 (`control/result`) |
|---|---|
| 가상 주방이 확인을 보냄 | `ok: true`, `rtt_ms` = 처음 보낸 때부터 확인까지 |
| 0.5초 안에 확인이 없음 | 같은 `seq`로 한 번 다시 보냄 → 확인이 오면 `ok: true, retries: 1` |
| 다시 보내도 확인이 없음 | `ok: false, retries: 1, reason: "no_ack"` (처음 보낸 지 약 1초 뒤) |
| 가상 주방이 거절 | `ok: false`, `reason`은 가상 주방이 준 것 (`no_heartbeat`, `invalid_command` 등) |
| 규격에 안 맞는 `control/command` | 가상 주방에 보내지 않고 `ok: false, reason: "invalid_command"` |

- `control/result`의 `session_id`는 받은 `control/command`의 것을 이어 쓴다 (발화 → 제어 지연을 한 세션에서 추적). `sensor/reading`·`system/heartbeat`는 자기 세션(`--session`)으로 낸다.
- 이미 끝난 명령의 늦은 확인은 무시한다.
- **알려진 한계**: 확인을 못 받아 실패로 끝낸 명령을, 가상 주방이 나중에 실행할 수 있다 (가상 주방이 잠깐 멈췄다 돌아온 경우). 보드는 실패한 뒤의 실제 상태를 `kitchen/state`로 확인해야 한다 — 상태를 버스로 올리는 것은 상황 인식(FUS-08)에서 필요해질 때 붙인다 (HW-22에서 재시도 정책과 함께 검토).

## 가짜 가상 주방 (`fake_kitchen.py`)

Unity 쪽이 맞춰야 할 동작([Unity 안내](../../recipes/unity-kitchen-link.md))을 Python으로 옮긴 기준 구현이다. 화면(`kitchen/frame`)은 없다.

- 명령을 적용하고 `kitchen/ack`를 보낸다. 같은 `seq`는 한 번만 실행하고 확인만 다시 보낸다 (최근 64개 기억).
- 가열 장치(`burner_1`, `burner_2`)의 온도를 규칙대로 바꿔 1초마다 `kitchen/temp`로 보낸다 (`common.kitchen_link.next_temperature`).
- 자체 안전장치: 생존 신호가 3초 끊기면 가열 장치를 끄고, 끊긴 동안에는 가열 장치를 켜는 명령을 거절한다 (`reason: "no_heartbeat"`). 온도가 265°C에 닿은 가열 장치는 스스로 끈다. 둘 다 `kitchen/state`의 `safe_stop`이 `true`가 된다.
- `kitchen/state`는 상태가 바뀔 때와 5초마다 보낸다.

## Spec

| 항목 | 내용 |
|---|---|
| 입력 | 버스 `control/command` · 연결 토픽 `kitchen/ack`, `kitchen/temp` |
| 출력 | 버스 `control/result`, `sensor/reading`, `system/heartbeat` · 연결 토픽 `kitchen/cmd`, `kitchen/heartbeat` |
| 설정값 | 확인 대기 0.5초, 재전송 1회, 생존 신호 1초 — `common/kitchen_link.py`의 상수 (규격이라 실행 옵션으로 두지 않았다) |
| 자원 | CPU, 모델 없음 |
| 가상 주방이 없으면 | 명령마다 약 1초 뒤 `ok: false, reason: "no_ack"`. 서비스는 계속 돈다 |
| 안전 | 이 서비스가 멈추면 생존 신호가 끊겨 가상 주방이 3초 뒤 가열 장치를 끈다 |

## 확인 기록

2026-10-06, M1 Pro Mac · mosquitto 2.1.2 (Docker, [`scripts/mosquitto/jarvis.conf`](../../scripts/mosquitto/jarvis.conf)) · 가짜 가상 주방 · 브로커 주소는 Mac의 랜 IP. **Unity·보드 아님.**

- `send ON hood` · `LEVEL burner_1 3` · `ON burner_2` · `OFF all` → 모두 `ok: true`, `rtt_ms` 1.1~1.5 (4건)
- 가짜 가상 주방을 멈춘 채 `send ON hood` → `ok: false, retries: 1, reason: no_ack`, 1,051.6 ms
- `kitchen_gw`를 4초 멈춤 → 켜 둔 화구의 온도가 오르다가 내려감 (115.1 → 110.5°C: 생존 신호가 끊겨 가상 주방이 화구를 끔)
- 녹화기(`recorder`, `#` 구독)에는 버스 메시지만 남고 `kitchen/*` 때문에 경고가 나지 않음
- 단위 테스트: `tests/kitchen_gw/test_service.py` (메모리 버스, 시간은 손으로 넘김)
