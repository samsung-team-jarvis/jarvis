# 인터페이스 규격 (v0.1 초안 — 팀 합의 전)

> 이 문서에 없는 필드·토픽은 쓰지 않는다. 바꿀 때는 맨 아래 변경 이력에 기록하고, [`common/messages.py`](../../common/messages.py)의 `TOPIC_REQUIRED_FIELDS`도 함께 고친다 (코드가 이 문서의 필수 필드를 검사한다).

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

### 2.1 비전 클래스 (VIS-02에서 확정)
후보: `pan, pot, burner_on, burner_off, fryer_basket, spatula, hand` + COCO 기본 `person` 활용 검토

### 2.2 장치 target (LLM-01에서 확정)
후보: `hood, burner_1, burner_2, fryer, timer, all`

### 2.3 State (FUS-01에서 확정)
`IDLE, PREHEAT, COOKING, UNATTENDED, DANGER, SAFE_STOP`

## 3. Function Call 스키마 (LLM 출력)

```json
{
  "action": "SET_LEVEL",
  "target": "hood",
  "level": 3,
  "duration_s": null,
  "need_confirmation": false
}
```

| Action | 의미 | 필수 파라미터 |
|---|---|---|
| `TURN_ON` | 켜기 | target |
| `TURN_OFF` | 끄기 | target |
| `SET_LEVEL` | 세기 조절 | target, level (범위 확정 필요, 예: 1~3) |
| `SET_TIMER` | 타이머 | duration_s, target? |
| `CANCEL_TIMER` | 타이머 취소 | target? |
| `CHECK_STATUS` | 상태 확인 | target? |
| `CHECK_RISK` | 위험 확인 | - |
| `EMERGENCY_STOP` | 긴급 정지 | - (target=all 고정) |
| `ASK_CLARIFY` | 재질문 | question |
| `UNSUPPORTED` | 지원 외 | - |

- LLM은 위 10개 중 **하나만** 출력. 그 외 값은 `valid=false` → 규칙 파서 대체.
- `REJECT`는 LLM Action이 아니라 Safety Guard의 판정(`guard/decision`).

### 3.1 학습 데이터 1건 (train.jsonl)
```json
{"instruction": "후드 좀 세게 틀어줘",
 "context": {"state": "COOKING", "temperature": 182, "detected_objects": ["pan", "burner_on"], "last_target": null},
 "output": {"action": "SET_LEVEL", "target": "hood", "level": 3, "need_confirmation": false},
 "meta": {"template_id": "t_017", "source": "seed|paraphrase|real", "split": "train"}}
```

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
