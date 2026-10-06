# Recipe: 가상 주방(Unity) ↔ 보드 연결

Unity 쪽을 만드는 사람이 읽는 안내다. 가상 주방이 보드와 무엇을 주고받아야 하는지, Unity 없이·보드 없이 어떻게 확인하는지를 적었다. 규격의 source of truth는 [interfaces](../docs/architecture/interfaces.md) §4, 숫자는 [`common/kitchen_link.py`](../common/kitchen_link.py)다.

> 2026-10-06 기준 **Unity와 실제로 주고받아 본 적은 없다.** 아래 확인 명령은 MQTT 명령줄 도구 기준이고, Unity C# 코드는 HW-16에서 작성한다. 막힌 곳을 이 문서에 추가한다.

## 한눈에

가상 주방은 보드의 MQTT 브로커에 접속해 토픽 6개만 다룬다. 봉투(`ts`, `session_id` 등)는 몰라도 된다 — 보드의 `kitchen_gw`가 처리한다.

| 가상 주방이 할 일 | 토픽 | 작업 |
|---|---|---|
| 명령을 받아 장치를 바꾼다 | `kitchen/cmd` 구독 | HW-16 |
| 바꿨다고 알린다 | `kitchen/ack` 발행 | HW-16 |
| 생존 신호가 끊기면 가열 장치를 끈다 | `kitchen/heartbeat` 구독 | HW-18 |
| 장치 상태를 알린다 | `kitchen/state` 발행 | HW-18 |
| 가열 장치의 온도를 계산해 보낸다 | `kitchen/temp` 발행 | HW-19 |
| 인식용 카메라 화면을 보낸다 | `kitchen/frame` 발행 | HW-20 |

## 1. 메시지

글자는 UTF-8 JSON이다 (`kitchen/frame`만 JPEG 바이트). QoS 0, retain 없음.

```text
kitchen/cmd        {"seq": 12, "cmd": "ON", "target": "hood", "value": 1}
kitchen/ack        {"seq": 12, "ok": true}
kitchen/temp       {"device_id": "burner_1", "temperature_c": 175.2}
kitchen/heartbeat  {"alive": true}
kitchen/state      {"devices": {"hood": {"on": true, "level": 1}, "burner_1": {"on": false, "level": 0}, "burner_2": {"on": false, "level": 0}}, "safe_stop": false}
```

명령은 세 가지다.

| `cmd` | `target` | `value` | 가상 주방에서 |
|---|---|---|---|
| `ON` | `hood` · `burner_1` · `burner_2` | `1` | 켠다 (세기 1) |
| `OFF` | 위 셋 또는 `all` | `0` | 끈다. `all`이면 전부 |
| `LEVEL` | `hood` · `burner_1` · `burner_2` | `1` · `2` · `3` | 세기를 바꾼다 (꺼져 있으면 켜면서) |

- 지금 장치는 3종이다. 튀김기·조명·에어컨·선풍기·음악·결제는 스키마 v0.2(LLM-13)에서 `target`이 추가된다. **모르는 `target`이 오면 무시하지 말고 `{"seq": …, "ok": false, "reason": "unknown_target"}`으로 답한다.**
- 타이머는 보드가 센다. 가상 주방은 끝났을 때 오는 `OFF`만 받는다.

## 2. 지켜야 할 동작

1. **같은 `seq`를 두 번 실행하지 않는다.** 보드는 0.5초 안에 확인을 못 받으면 같은 `seq`로 한 번 다시 보낸다. 이미 처리한 `seq`가 다시 오면 장치는 그대로 두고 `kitchen/ack`만 다시 보낸다 (최근 `seq` 몇 개를 기억해 둔다).
2. **장치를 바꾼 뒤에 `kitchen/ack`를 보낸다.** 보드는 이 확인을 받은 뒤에 "후드를 켰습니다"라고 말한다.
3. **시작하면 모든 장치가 꺼져 있다.**
4. **`kitchen/heartbeat`가 3초 동안 안 오면 가열 장치(`burner_1`, `burner_2`)를 끈다.** 후드는 끄지 않는다. 이때 `kitchen/state`의 `safe_stop`을 `true`로 보낸다.
5. **온도가 265°C에 닿은 가열 장치는 스스로 끈다** (`safe_stop: true`).
6. `kitchen/state`는 상태가 바뀔 때마다, 그리고 5초에 한 번 보낸다.
7. MQTT 메시지는 Unity의 메인 스레드가 아닌 곳에서 도착한다. 장치를 바꾸는 코드는 메인 스레드에서 실행되게 넘긴다 ([Unity 결정](../docs/decisions/2026-10-05-unity-virtual-kitchen.md)).

## 3. 가상 온도 (HW-19)

가열 장치마다 온도 하나를 두고 1초마다 아래 식으로 바꾼 뒤 `kitchen/temp`로 보낸다. 시연용 설계값이다.

```text
T ← T + (목표 − T) × 0.05        목표: 꺼짐 25 · 세기 1 → 120 · 세기 2 → 180 · 세기 3 → 270 (°C)
```

기준 구현은 Python `common.kitchen_link.next_temperature`다. 25°C에서 세기 3으로 두면 41초 뒤 240°C, 76초 뒤 265°C를 넘는다 (같은 식으로 계산한 값). Unity 결과가 이와 다르면 식을 잘못 옮긴 것이다.

## 4. 캡처 화면 (HW-20)

- 인식용 카메라(조리대와 조리 구역이 한 화면에 들어오게 고정)를 640×360으로 그려 JPEG로 압축해 `kitchen/frame`에 바이트 그대로 보낸다. 1초에 4장.
- 사용자가 보는 화면의 카메라와 따로 둔다. 겹쳐 띄우는 글자·창은 인식용 화면에 넣지 않는다.

## 5. 확인 방법

### 5.1 보드 없이 (자기 PC에서)

자기 PC에 MQTT 브로커를 띄우고 명령줄 도구로 보드 역할을 대신한다. mosquitto를 설치하면 `mosquitto_pub`·`mosquitto_sub`가 함께 들어 있다 ([local-development](../docs/workflows/local-development.md)).

```bash
mosquitto_sub -t 'kitchen/#' -v                                   # 창 1: 오가는 메시지 보기 (kitchen/frame은 깨진 글자로 보인다)
mosquitto_pub -t kitchen/cmd -m '{"seq":1,"cmd":"ON","target":"hood","value":1}'     # 창 2: 후드 켜기
mosquitto_pub -t kitchen/cmd -m '{"seq":1,"cmd":"ON","target":"hood","value":1}'     # 같은 seq 다시 → 확인만 다시 와야 한다
mosquitto_pub -t kitchen/cmd -m '{"seq":2,"cmd":"LEVEL","target":"burner_1","value":3}'
mosquitto_pub -t kitchen/cmd -m '{"seq":3,"cmd":"OFF","target":"all","value":0}'
```

Windows PowerShell에서는 작은따옴표 안의 큰따옴표가 지워질 수 있다. 그때는 JSON을 파일에 저장하고 `mosquitto_pub -t kitchen/cmd -f cmd.json`으로 보낸다.

생존 신호는 1초에 한 번 보내야 가열 장치가 꺼지지 않는다. 확인할 때는 반복해서 보낸다.

```bash
while true; do mosquitto_pub -t kitchen/heartbeat -m '{"alive":true}'; sleep 1; done    # 멈추면 3초 뒤 가열 장치가 꺼져야 한다
```

### 5.2 확인 목록

| 작업 | 확인 |
|---|---|
| HW-16 | `kitchen/cmd`의 `ON`/`OFF`로 후드가 켜지고 꺼지며, 그때마다 `kitchen/ack`가 온다. 같은 `seq`를 다시 보내면 장치는 그대로이고 확인만 온다. 모르는 `target`에는 `ok: false`가 온다 |
| HW-18 | 생존 신호를 멈추면 3초 뒤 가열 장치가 꺼지고 `safe_stop: true`가 온다. 후드는 그대로다 |
| HW-19 | 화구를 세기 3으로 두면 `kitchen/temp`가 1초마다 오르고, 265°C에서 스스로 꺼진다 |
| HW-20 | `kitchen/frame`이 1초에 4장 온다. 받은 바이트를 `.jpg`로 저장하면 640×360 그림이 열린다 |

### 5.3 보드와 함께

보드의 브로커가 같은 네트워크의 접속을 받도록 설정하고([`scripts/mosquitto/jarvis.conf`](../scripts/mosquitto/jarvis.conf), 보드 미검증), Unity의 접속 주소를 보드의 IP와 포트 1883으로 바꾼다. 보드 쪽 `kitchen_gw`(HW-17)가 뜨면 `python -m bench.latency`로 왕복 시간을 볼 수 있다.

## 관련

- 규격: [interfaces](../docs/architecture/interfaces.md) §4 · 결정: [연결 방식](../docs/decisions/2026-10-06-kitchen-link.md), [Unity](../docs/decisions/2026-10-05-unity-virtual-kitchen.md)
- 보드 쪽 구현과 가짜 가상 주방: HW-17
