# 인터페이스 규격 (v0.1)

> 2026-10-02 확정 (결정: 이현종, #39). §1·§2 봉투·토픽·State(FUS-01)와 §3 Function Call(LLM-01)은 확정, §2.1 비전 클래스(VIS-02)·§4 BLE 코드표(HW-01)는 아직 초안. 상황 인식 구현(③) 중 State를 바꿔야 하면 변경 이력에 남기고 바꾼다.

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
| `session_id` | 실행/녹화 세션 ID (데이터 분할 단위) |
| `source` | 발행 서비스 이름 |
| `type` | 토픽 이름과 동일 |

## 2. 토픽

| 토픽 | 발행 | payload (초안) |
|---|---|---|
| `stt/text` | audio_svc | `{text, wake: bool, conf?, audio_ms, stt_ms, speech_end_mono}` |
| `vision/objects` | vision_svc | `{objects:[{cls, conf, bbox:[x1,y1,x2,y2]}], frame_id, pre_ms, npu_ms, post_ms}` |
| `sensor/reading` | ble_gw | `{device_id, temperature_c, current_a, raw?}` |
| `fusion/state` | fusion_svc | `{state, prev_state, evidence:{...}, risk: none\|warn\|danger}` |
| `llm/function_call` | llm_svc | `{call: <§3>, raw_text, valid: bool, fallback: bool, gen_ms, tokens}` |
| `guard/decision` | safety_guard | `{call, decision: ALLOW\|REJECT\|ASK, reason}` |
| `control/command` | safety_guard | `{seq, cmd, target, value}` |
| `control/result` | ble_gw | `{seq, ok: bool, retries, rtt_ms}` |
| `system/heartbeat` | 각 서비스 | `{alive: true}` |

- `llm/function_call`을 규칙 파서가 만들면(LLM 연결 전, 또는 LLM 출력 검증 실패 시 대체): `fallback: true`, `tokens: 0`, `raw_text`는 파서에 넣은 명령 문장, `gen_ms`는 파싱 시간. `session_id`는 원래 `stt/text`의 것을 이어 쓴다.

### 2.1 비전 클래스 (VIS-02에서 확정)
후보: `pan, pot, burner_on, burner_off, fryer_basket, spatula, hand` + COCO 기본 `person` 활용 검토

### 2.2 장치 target (LLM-01 확정)

| target | 장치 | 모형 (④) |
|---|---|---|
| `hood` | 후드 (환풍기) | USB 팬, 세기 1~3 (PWM) |
| `burner_1` | 1번 화구 | LED 또는 릴레이, 세기 1~3 (PWM 밝기) |
| `burner_2` | 2번 화구 | 〃 |
| `all` | 전체 (끄기·타이머·상태 확인·긴급 정지에만) | — |

- 튀김기는 화구 위에서 쓰는 것으로 보고 따로 두지 않는다. 타이머는 장치가 아니라 Action(`SET_TIMER`)이다.
- 켤 때(`TURN_ON`) 세기는 1. BLE 코드표 번호는 HW-01에서 정한다.

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

## 4. BLE (Pi ↔ ESP32)

| 특성 | 방향 | 내용 |
|---|---|---|
| `cmd` | Pi → ESP32 (write) | 명령 패킷 |
| `ack` | ESP32 → Pi (notify) | `seq`, 결과 코드 |
| `sensor` | ESP32 → Pi (notify) | 온도·전류 |
| `heartbeat` | Pi → ESP32 (write) | 주기적 생존 신호 |

명령 패킷 (초안, 바이트):
`[seq:u16][cmd:u8][target:u8][value:i16][crc8:u8]`
- 코드표(cmd/target 번호)는 HW-01에서 확정.
- ACK 미수신 시 재시도 (횟수·타임아웃 HW-01에서 확정). `seq`로 중복 실행 방지.

## 변경 이력

| 날짜 | 버전 | 변경 | 작성 |
|---|---|---|---|
| 2026-10-01 | v0.1 | 최초 초안 (5주차 발표자료 기반) | - |
| 2026-10-02 | v0.1 | §3에 LLM 생성 형식(SUDA식 함수 토큰)과 버스 JSON의 관계 명시 — 필드 변경 없음 (#25) | 이현종 |
| 2026-10-02 | v0.1 | §2.2 target 확정(hood·burner_1·burner_2·all), §2.3 State 확정, §3 Function Call 확정 — Action별 파라미터·값 범위, `need_confirmation` 삭제(Guard가 판정), `ASK_CLARIFY.question` → `for_action`·`missing`, 함수 토큰 문법, 예시 (#39, LLM-01·FUS-01) | 이현종 |
| 2026-10-02 | v0.1 | §2 `llm/function_call`을 규칙 파서가 만들 때의 필드 의미 명시 — 필드 변경 없음 (#41) | 이현종 |
