# 인터페이스 규격 (v0.1)

> 2026-10-02 확정 (결정: 이현종, #39). §1·§2 봉투·토픽·State(FUS-01)와 §3 Function Call(LLM-01)은 확정, §2.1 비전 클래스(VIS-02)는 아직 초안. §4 가상 주방 연결은 2026-10-06 확정 (HW-14, #80). 상황 인식 구현(③) 중 State를 바꿔야 하면 변경 이력에 남기고 바꾼다.

> **2026-10-05**: 시연 환경을 가상 주방으로 바꾸고 장치를 8종으로 넓히기로 했다 ([decision](../decisions/2026-10-05-virtual-kitchen-demo.md)). 이 문서의 v0.1 규격(봉투·토픽·Function Call)은 코드와 맞춘 상태 그대로 두고, 바뀔 내용은 [§5 v0.2 예정 변경](#5-v02-예정-변경-가상-주방--장치-8종)에 모았다. v0.2는 LLM-13(스키마)·HW-14(연결 규격)에서 코드와 함께 확정한다.

> 이 문서에 없는 필드·토픽은 쓰지 않는다. 바꿀 때는 맨 아래 변경 이력에 기록하고, 코드도 함께 고친다 — 토픽 필수 필드는 [`common/messages.py`](../../common/messages.py)의 `TOPIC_REQUIRED_FIELDS`, §3 명령 스키마는 [`common/function_call.py`](../../common/function_call.py) (코드가 이 문서의 규칙을 검사한다).

## 1. 메시지 봉투 (모든 메시지 공통)

```json
{
  "v": 1,
  "ts": 1730000000.123,
  "mono": 12345.678,
  "session_id": "s_20261012_01",
  "source": "vision_svc",
  "type": "vision/objects",
  "payload": {}
}
```

| 필드 | 설명 |
|---|---|
| `v` | 봉투 버전 |
| `ts` | Pi 기준 유닉스 시각(초, 소수) |
| `mono` | Pi 단조 시계(초) — 지연 계산용 |
| `session_id` | 실행/녹화 세션 ID (데이터 분할 단위). **다른 메시지를 받아 만든 메시지는 받은 메시지의 `session_id`를 그대로 쓴다** (발화 → 명령 → 판정 → 제어를 지연 분해에서 이어 붙이는 기준, [bench](../../bench/README.md)) |
| `source` | 발행 서비스 이름 |
| `type` | 토픽 이름과 동일 |

## 2. 토픽

| 토픽 | 발행 | payload (초안) |
|---|---|---|
| `stt/text` | audio_svc | `{text, wake: bool, conf?, audio_ms, stt_ms, speech_end_mono}` |
| `vision/objects` | vision_svc | `{objects:[{cls, conf, bbox:[x1,y1,x2,y2]}], frame_id, pre_ms, npu_ms, post_ms}` |
| `sensor/reading` | kitchen_gw | `{device_id, temperature_c, current_a?, raw?}` |
| `fusion/state` | fusion_svc | `{state, prev_state, evidence:{...}, risk: none\|warn\|danger}` |
| `llm/function_call` | llm_svc | `{call: <§3>, raw_text, valid: bool, fallback: bool, gen_ms, tokens}` |
| `guard/decision` | safety_guard | `{call, decision: ALLOW\|REJECT\|ASK, reason}` |
| `control/command` | safety_guard | `{seq, cmd, target, value}` |
| `control/result` | kitchen_gw | `{seq, ok: bool, retries, rtt_ms}` |
| `system/heartbeat` | 각 서비스 | `{alive: true}` |

- `control/command`의 값 (HW-14 확정, 코드: [`common/kitchen_link.py`](../../common/kitchen_link.py) `validate_command`·`command_for`):

  | `cmd` | `target` | `value` | 만드는 Action |
  |---|---|---|---|
  | `ON` | 개별 장치 (`all` 불가) | `1` (켤 때 세기 1) | `TURN_ON` |
  | `OFF` | 개별 장치 또는 `all` | `0` | `TURN_OFF`, `EMERGENCY_STOP`(`all`), 타이머 만료 |
  | `LEVEL` | 개별 장치 | `1`·`2`·`3` | `SET_LEVEL` |

  `seq`는 0 이상의 정수이고 `safety_guard`가 세션 안에서 하나씩 올린다. 타이머는 보드가 세고, 끝났을 때 `OFF`를 보낸다 (가상 주방은 타이머를 모른다).
- `sensor/reading`의 `device_id`는 가열 장치 이름(`burner_1`, `burner_2`)이다. 전류(`current_a`)는 가상 주방에 없어 선택 필드로 바꿨다.
- `llm/function_call`을 규칙 파서가 만들면(LLM 연결 전, 또는 LLM 출력 검증 실패 시 대체): `fallback: true`, `tokens: 0`, `raw_text`는 파서에 넣은 명령 문장, `gen_ms`는 파싱 시간. `session_id`는 원래 `stt/text`의 것을 이어 쓴다.

### 2.1 비전 클래스 (VIS-02에서 확정)
후보: `pan, pot, burner_on, burner_off, fryer_basket, spatula, hand` + COCO 기본 `person` 활용 검토

### 2.2 장치 target (LLM-01 확정)

| target | 장치 | 가상 주방 (④) |
|---|---|---|
| `hood` | 후드 (환풍기와 같은 장치) | 표시등과 바람, 세기 1~3 |
| `burner_1` | 1번 화구 | 불꽃 크기, 세기 1~3 |
| `burner_2` | 2번 화구 | 〃 |
| `all` | 전체 (끄기·타이머·상태 확인·긴급 정지에만) | — |

- 튀김기는 화구 위에서 쓰는 것으로 보고 따로 두지 않는다. 타이머는 장치가 아니라 Action(`SET_TIMER`)이다.
- 켤 때(`TURN_ON`) 세기는 1.
- v0.1은 장치 3종이다. 튀김기는 v0.2에서 따로 둔다 (§5).

### 2.3 State (FUS-01 확정)
`IDLE, PREHEAT, COOKING, UNATTENDED, DANGER, SAFE_STOP` — 전이 조건은 상황 인식(FUS-05)에서 정한다.

## 3. Function Call 스키마 (LLM 출력)

명령은 두 가지로 표현한다. 코드: [`common/function_call.py`](../../common/function_call.py) (`validate`, `parse_tokens`, `to_tokens`). 결정 배경: [decision](../decisions/2026-10-02-function-call-schema.md).

- **버스 JSON** — `llm/function_call`의 `call`, 규칙 파서 출력, Safety Guard 입력. `action`과 그 Action의 파라미터만 넣는다 (없는 파라미터는 키를 빼고, `null`로 채우지 않는다).
  ```json
  {"action": "SET_LEVEL", "target": "hood", "level": 3}
  ```
- **함수 토큰** — LLM이 생성하는 문자열 (SUDA 방식, [Q-10](../decisions/open-questions.md)). `llm_svc`가 `parse_tokens`로 버스 JSON으로 바꾼다. 형식이 틀리면 `valid=false` → 규칙 파서로 대체.
  ```text
  <jarvis_3>(target=hood, level=3)<jarvis_end>
  ```

### 3.1 Action

| 번호 | Action | 의미 | 파라미터 (JSON) | 함수 토큰 인자 |
|---|---|---|---|---|
| 1 | `TURN_ON` | 켜기 | `target`: hood · burner_1 · burner_2 (all 불가) | `target` |
| 2 | `TURN_OFF` | 끄기 | `target`: hood · burner_1 · burner_2 · all | `target` |
| 3 | `SET_LEVEL` | 세기 조절 | `target`: hood · burner_1 · burner_2, `level`: 1 · 2 · 3 (약·중·강) | `target`, `level` |
| 4 | `SET_TIMER` | 타이머 | `duration_s`: 1~3600 정수, `target`?: hood · burner_1 · burner_2 · all | `min`, `sec`, `target`? |
| 5 | `CANCEL_TIMER` | 타이머 취소 | `target`? (없으면 모든 타이머) | `target`? |
| 6 | `CHECK_STATUS` | 상태 확인 | `target`? (없으면 전체) | `target`? |
| 7 | `CHECK_RISK` | 위험 확인 | — | — |
| 8 | `EMERGENCY_STOP` | 긴급 정지 | `target`: all 고정 | 없음 (`llm_svc`가 all을 채움) |
| 9 | `ASK_CLARIFY` | 되묻기 | `for_action`: Action 또는 `null`, `missing`: target · level · duration 목록 | 아래 3.2 |
| 10 | `UNSUPPORTED` | 지원 외 요청 | — | — |

- LLM은 한 번에 **하나만** 출력한다. 번호는 바꾸지 않는다 (학습 데이터·변환 모델이 번호를 쓴다).
- **타이머**: `target`이 있으면 끝날 때 그 장치를 끈다(Safety Guard를 거친 `TURN_OFF`). 없으면 알림(부저·음성)만. 장치마다 타이머 1개, 같은 장치에 다시 맞추면 덮어쓴다.
- **세기**: "약하게/중간/세게·최대" → 1/2/3. "조금 더"처럼 지금 세기 기준의 상대 조절은 v0에서 다루지 않고 `level=?`로 되묻는다.
- **`TURN_OFF all`과 `EMERGENCY_STOP`의 차이**: 앞은 평소 끄기, 뒤는 위험 상황의 즉시 차단(긴급 빠른 경로 FUS-04, `SAFE_STOP` 상태로).
- 확인이 필요한 명령인지는 LLM이 아니라 **Safety Guard가 판정**한다 (`guard/decision`의 `ASK`). 그래서 명령에 `need_confirmation`을 두지 않는다.
- `REJECT`는 LLM Action이 아니라 Safety Guard의 판정이다.

### 3.2 함수 토큰 문법

```text
<jarvis_{번호}>({키}={값}, {키}={값})<jarvis_end>
```

- 키: `target`, `level`, `min`, `sec` (해당 Action이 받는 것만). 순서 무관, 쉼표 뒤 공백 허용, 같은 키 반복 금지.
- 값: target 이름, 숫자(아라비아 숫자, "삼 분" → `min=3`), 또는 `?`.
- 시간은 `min`·`sec`로 쓰고 `llm_svc`가 `duration_s = min×60 + sec`로 바꾼다 (작은 모델에게 곱셈을 시키지 않는다).
- **`?` = 말에 빠진 값** (SUDA의 -1). 하려는 Action 번호에 `?`를 넣으면 `ASK_CLARIFY {for_action, missing}`이 된다. 무엇을 하려는지도 모르면 `<jarvis_9>()`.
- 끝 토큰 `<jarvis_end>`는 생성 종료·캘리브레이션 절단(`calib_stop_at`) 기준이다. 토크나이저에 특수 토큰으로 넣을지는 LLM 학습 단계에서 정한다.

### 3.3 예시

| 발화 (호출어 뒤) | 함수 토큰 | 버스 JSON |
|---|---|---|
| 후드 켜 줘 | `<jarvis_1>(target=hood)<jarvis_end>` | `{"action":"TURN_ON","target":"hood"}` |
| 다 꺼 줘 | `<jarvis_2>(target=all)<jarvis_end>` | `{"action":"TURN_OFF","target":"all"}` |
| 2번 불 약하게 | `<jarvis_3>(target=burner_2, level=1)<jarvis_end>` | `{"action":"SET_LEVEL","target":"burner_2","level":1}` |
| 3분 뒤에 1번 화구 꺼 줘 | `<jarvis_4>(target=burner_1, min=3)<jarvis_end>` | `{"action":"SET_TIMER","target":"burner_1","duration_s":180}` |
| 타이머 3분 30초 | `<jarvis_4>(min=3, sec=30)<jarvis_end>` | `{"action":"SET_TIMER","duration_s":210}` |
| 타이머 꺼 | `<jarvis_5>()<jarvis_end>` | `{"action":"CANCEL_TIMER"}` |
| 1번 화구 켜져 있어? | `<jarvis_6>(target=burner_1)<jarvis_end>` | `{"action":"CHECK_STATUS","target":"burner_1"}` |
| 지금 위험해? | `<jarvis_7>()<jarvis_end>` | `{"action":"CHECK_RISK"}` |
| 멈춰 | `<jarvis_8>()<jarvis_end>` | `{"action":"EMERGENCY_STOP","target":"all"}` |
| 불 켜 줘 (몇 번인지 없음) | `<jarvis_1>(target=?)<jarvis_end>` | `{"action":"ASK_CLARIFY","for_action":"TURN_ON","missing":["target"]}` |
| 후드 조금 더 | `<jarvis_3>(target=hood, level=?)<jarvis_end>` | `{"action":"ASK_CLARIFY","for_action":"SET_LEVEL","missing":["level"]}` |
| 타이머 맞춰 줘 | `<jarvis_4>(min=?)<jarvis_end>` | `{"action":"ASK_CLARIFY","for_action":"SET_TIMER","missing":["duration"]}` |
| 그거 해 줘 | `<jarvis_9>()<jarvis_end>` | `{"action":"ASK_CLARIFY","for_action":null,"missing":[]}` |
| 오늘 날씨 어때? | `<jarvis_10>()<jarvis_end>` | `{"action":"UNSUPPORTED"}` |

같은 표가 [`tests/common/test_function_call.py`](../../tests/common/test_function_call.py)의 `EXAMPLES`로 검사된다.

### 3.4 학습 데이터 1건 (train.jsonl)

```json
{"instruction": "후드 좀 세게 틀어줘",
 "context": {"state": "COOKING", "temperature": 182, "detected_objects": ["pan", "burner_on"], "last_target": null},
 "output": {"action": "SET_LEVEL", "target": "hood", "level": 3},
 "meta": {"template_id": "t_017", "source": "seed|paraphrase|real", "split": "train"}}
```

학습용 정답 문자열은 `to_tokens(output)`으로 만든다 → `<jarvis_3>(target=hood, level=3)<jarvis_end>`.

## 4. 보드 ↔ 가상 주방 (v0.1 확정, HW-14)

가상 주방은 Unity다 ([decision](../decisions/2026-10-05-unity-virtual-kitchen.md)). 보드의 MQTT 브로커에 직접 접속하지만 **버스의 봉투 메시지는 쓰지 않는다.** 봉투 없는 짧은 JSON을 `kitchen/*` 토픽으로 주고받고, 보드의 `kitchen_gw`가 버스 메시지로 옮긴다 ([decision](../decisions/2026-10-06-kitchen-link.md)). 코드: [`common/kitchen_link.py`](../../common/kitchen_link.py) (토픽·상수·검사). Unity 쪽 안내: [recipe](../../recipes/unity-kitchen-link.md).

### 4.1 구조

```text
 버스 (봉투, 보드 시계)        kitchen_gw (보드)          가상 주방 (Unity, PC)
 control/command  ─────────▶  kitchen/cmd        ─────▶  장치를 바꾼다
 control/result   ◀─────────  kitchen/ack        ◀─────  바꿨다고 알린다
 sensor/reading   ◀─────────  kitchen/temp       ◀─────  온도를 계산해 보낸다 (1Hz)
                              kitchen/heartbeat  ─────▶  3초 끊기면 가열 장치 OFF (L0)
                              kitchen/state      ◀─────  장치 상태
 vision_svc 입력  ◀────────────────────────────  kitchen/frame  (인식용 카메라, 4fps)
```

- **시각은 보드가 찍는다.** 버스 메시지의 `ts`·`mono`는 `kitchen_gw`가 받은 순간의 보드 시계다. 가상 주방 PC의 시계는 쓰지 않는다 (지연 측정이 한 시계 안에서 계산된다, [overview](./overview.md) §5).
- 가상 주방은 봉투·`session_id`를 몰라도 된다. `kitchen_gw`가 받은 `control/command`의 `session_id`를 `control/result`에 이어 쓴다.

### 4.2 토픽

| 토픽 | 방향 | 주기 | payload 예시 |
|---|---|---|---|
| `kitchen/cmd` | 보드 → 가상 주방 | 명령이 있을 때 | `{"seq": 12, "cmd": "LEVEL", "target": "burner_2", "value": 3}` |
| `kitchen/ack` | 가상 주방 → 보드 | 명령마다 1번 | `{"seq": 12, "ok": true}` |
| `kitchen/temp` | 가상 주방 → 보드 | 가열 장치마다 1초에 1번 | `{"device_id": "burner_1", "temperature_c": 175.2}` |
| `kitchen/heartbeat` | 보드 → 가상 주방 | 1초에 1번 | `{"alive": true}` |
| `kitchen/state` | 가상 주방 → 보드 | 상태가 바뀔 때 + 5초에 1번 | `{"devices": {"hood": {"on": true, "level": 2}, "burner_1": {"on": false, "level": 0}, "burner_2": {"on": false, "level": 0}}, "safe_stop": false}` |
| `kitchen/frame` | 가상 주방 → 보드 | 1초에 4장 | JPEG 바이트 그대로 (JSON 아님). 640×360 |

- 글자는 UTF-8, JSON 키는 위 이름 그대로. MQTT QoS 0, retain 없음.
- `kitchen/cmd`의 값은 §2의 `control/command`와 같다.
- `kitchen/ack`의 `ok: false`는 가상 주방이 명령을 실행하지 않았다는 뜻이다. 이유를 `reason`(문자열)에 넣을 수 있다.
- `kitchen/state`의 `level`은 꺼져 있으면 0. `safe_stop`은 가상 주방이 스스로 가열 장치를 끈 상태(§4.4)다.
- 같은 표의 예시가 [`tests/common/test_kitchen_link.py`](../../tests/common/test_kitchen_link.py)에서 검사된다.

### 4.3 명령과 확인

1. `kitchen_gw`가 `kitchen/cmd`를 보내고 0.5초 동안 같은 `seq`의 `kitchen/ack`를 기다린다.
2. 없으면 **같은 `seq`로 한 번** 다시 보낸다. 그래도 없으면 `control/result`를 `ok: false, retries: 1`로 낸다.
3. 가상 주방은 이미 처리한 `seq`를 다시 받으면 **장치를 다시 바꾸지 않고** 확인만 다시 보낸다 (최근 `seq`를 기억한다).
4. `control/result`의 `rtt_ms`는 `kitchen_gw`가 처음 보낸 때부터 확인을 받을 때까지의 시간이다.

### 4.4 가상 주방의 자체 안전장치 (안전 계층 L0)

보드와 무관하게 가상 주방 안에서 동작한다.

- `kitchen/heartbeat`가 **3초** 동안 오지 않으면 모든 가열 장치를 끈다.
- 가열 장치의 온도가 **265°C**에 닿으면 그 장치를 끈다.
- 둘 중 하나가 일어나면 `kitchen/state`의 `safe_stop`을 `true`로 보낸다. 생존 신호가 돌아오고 명령을 새로 받으면 `false`로 돌아간다.
- 시작 직후에는 모든 장치가 꺼져 있다.

### 4.5 가상 온도 규칙 (시연용 설계값)

실제 조리 온도를 잰 값이 아니다. 과열을 1분 남짓에 재현하도록 정한 값이고, 써 보고 조정한다 (HW-19·FUS-05).

- 가열 장치마다 온도를 하나 둔다. 1초마다 목표 온도와의 차이의 5%씩 다가간다: `T ← T + (목표 − T) × 0.05`
- 목표 온도: 꺼짐 25°C · 세기 1 → 120°C · 세기 2 → 180°C · 세기 3 → 270°C
- 기준 구현: `common.kitchen_link.next_temperature` (Unity 코드도 같은 식을 쓴다)
- 주의·위험 구간(200°C·240°C)과 방치 판단은 가상 주방이 아니라 보드(`fusion_svc`·`safety_guard`)가 한다 — 값은 FUS-05에서 확정.

### 4.6 접속

- 가상 주방 PC와 보드를 랜선으로 잇고, Unity가 보드의 mosquitto(포트 1883)에 접속한다.
- mosquitto 2는 기본 설정에서 같은 기기의 접속만 받는다. 설정 예시: [`scripts/mosquitto/jarvis.conf`](../../scripts/mosquitto/jarvis.conf) (**보드 미검증**). 인터넷에 연결된 망에서는 쓰지 않는다.
- 화면에 겹쳐 띄울 정보(상태·들은 말·판단 이유)의 전달은 UI-01에서 정한다.

## 5. v0.2 예정 변경 (가상 주방 · 장치 8종)

아직 코드에 반영하지 않았다. 확정하면 위 본문과 코드를 함께 고치고 이 절을 지운다.

| 항목 | v0.1 (지금 코드) | v0.2 (예정) | 확정 작업 |
|---|---|---|---|
| 장치 target | `hood`, `burner_1`, `burner_2`, `all` | + 튀김기, 조명, 에어컨, 선풍기, 음악 (이름은 LLM-13에서. 기존 이름·번호는 바꾸지 않고 덧붙인다) | LLM-13 |
| 환풍기 | 후드를 부르는 다른 말 | 그대로 (같은 장치) | — |
| Action | 10개 (§3.1) | + 결제 요청, 금액 확인 (번호 11~). 결제 요청은 Safety Guard가 확인(`ASK`)을 거친 뒤 실행 | LLM-13, FUS-03 |
| 세기 | 1~3 (후드·화구) | 장치별 값의 범위 추가 (에어컨 온도, 조명 밝기, 음량) | LLM-13 |
| 캡처 화면 | — | `kitchen/frame` (§4.2)를 `vision_svc`가 직접 구독해 받은 시각을 찍는다 | HW-20·VIS-08 |
| 비전 클래스 (§2.1) | 후보 7개 + person | 가상 주방 장면에서 실제로 보이는 물체로 확정 | VIS-02 |

- v0.1 데이터에서 "조명 켜줘"·"에어컨 꺼줘"·"볼륨 줄여 줘"는 `UNSUPPORTED`가 정답이다. v0.2에서 정답이 바뀌므로 데이터 v2를 다시 만들고 기준선을 다시 잰다 (LLM-14).

## 변경 이력

| 날짜 | 버전 | 변경 | 작성 |
|---|---|---|---|
| 2026-10-01 | v0.1 | 최초 초안 (5주차 발표자료 기반) | - |
| 2026-10-02 | v0.1 | §3에 LLM 생성 형식(SUDA식 함수 토큰)과 버스 JSON의 관계 명시 — 필드 변경 없음 (#25) | 이현종 |
| 2026-10-02 | v0.1 | §2.2 target 확정(hood·burner_1·burner_2·all), §2.3 State 확정, §3 Function Call 확정 — Action별 파라미터·값 범위, `need_confirmation` 삭제(Guard가 판정), `ASK_CLARIFY.question` → `for_action`·`missing`, 함수 토큰 문법, 예시 (#39, LLM-01·FUS-01) | 이현종 |
| 2026-10-02 | v0.1 | §2 `llm/function_call`을 규칙 파서가 만들 때의 필드 의미 명시 — 필드 변경 없음 (#41) | 이현종 |
| 2026-10-02 | v0.1 | §1 `session_id` 이어 쓰기 규칙 명시 (지연 분해 연결 기준) — 필드 변경 없음 (#45) | 이현종 |
| 2026-10-05 | v0.1 | 시연 환경 변경(가상 주방) 반영: §2 발행 서비스 `ble_gw` → `kitchen_gw`, §2.2 모형 설명, §4 BLE 규격 삭제 → 보드 ↔ 가상 주방, §5 v0.2 예정 변경 추가 — **v0.1 필드·코드 변경 없음** (#73) | 이현종 |
| 2026-10-06 | v0.1 | §4 보드 ↔ 가상 주방 확정: `kitchen/*` 연결 토픽 6개, 재시도·중복 방지, 자체 안전장치, 가상 온도 규칙. §2 `control/command` 값(`ON`·`OFF`·`LEVEL`) 확정, `sensor/reading`의 `current_a`를 선택 필드로 (#80, HW-14) | 이현종 |
