# safety_guard — 명령 판정 (안전 계층 L1)

명령 해석 결과(`llm/function_call`)를 지금 주방 상태(`fusion/state`)로 판정해 `guard/decision`을 발행하고, 허용된 제어만 `control/command`로 보낸다. **`control/command`는 이 서비스만 발행한다**. 그래서 LLM 출력이 Guard를 건너뛰어 장치로 가는 경로가 없다 ([안전 3계층](../../docs/decisions/2026-10-01-safety-layers.md), [LLM은 말 그대로·Guard가 판단](../../docs/decisions/2026-10-02-llm-literal-guard-decides.md)). PLAN FUS-03·FUS-04.

```text
fusion/state ───────────────▶ 지금 상태 (마지막 값)
llm/function_call ─▶ 판정 ─▶ guard/decision (ALLOW | REJECT + 이유) ─▶ 음성 응답(audio_svc)
                             └─ ALLOW이고 장치를 움직이는 명령 ─▶ control/command ─▶ kitchen_gw
stt/text ─▶ 긴급어? ─▶ 바로 EMERGENCY_STOP (명령 해석을 기다리지 않음)
```

## 실행

```bash
python -m services.safety_guard                          # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.safety_guard --assume-state COOKING   # 상황 인식(fusion_svc) 없이 화구까지 켜 볼 때
python -m services.safety_guard judge '{"action":"TURN_ON","target":"burner_1"}' --state DANGER
```

런처(`scripts/launch.py`)는 recorder 다음에 띄운다 (명령보다 먼저 떠 있어야 한다).

## 판정 규칙 (`rules.py`)

| 명령 | 평소 (IDLE·PREHEAT·COOKING) | 위험 (UNATTENDED·DANGER·SAFE_STOP) · 상태 모름 |
|---|---|---|
| 형식이 틀린 명령 (`common.function_call.validate` 실패) | REJECT | REJECT |
| 화구 켜기·세기 바꾸기 (`TURN_ON`·`SET_LEVEL` + `burner_1`·`burner_2`) | ALLOW | **REJECT** |
| 그 밖의 모든 명령 (끄기·긴급 정지·후드·타이머·상태/위험 확인·되묻기·지원 외) | ALLOW | ALLOW |

- **끄는 쪽은 어떤 상태에서도 막지 않는다.** 막으면 더 위험해진다.
- 위험 상태에서는 세기를 **낮추는** 명령도 막는다. Guard는 지금 세기를 모르므로 "낮춤"과 "꺼진 화구를 켜기"를 구분할 수 없다. 대신 REJECT 이유로 "끄려면 꺼 달라고 말해 주세요"를 안내한다.
- `fusion/state`를 한 번도 받지 못했으면 **상태 모름 = 위험 상태처럼** 판정한다. 그래서 상황 인식이 없을 때도 후드는 켜지지만(Gate 2) 화구는 켜지지 않는다. 개발할 때는 `--assume-state`로 가정 상태를 준다.
- REJECT 이유는 음성 응답이 "지금은 ○○을 제어할 수 없어요." 뒤에 붙여 읽는다 ([responses](../audio_svc/responses.py)).
- 위험 상황 Hard Negative 34건(`data/llm/hard_negative_v1.jsonl`의 `expect_guard`)과 이 규칙의 판정이 같은지 테스트로 검사한다. 규칙을 바꾸면 데이터의 `expect_guard`도 같이 바꾼다.

## 긴급 빠른 경로 (`emergency.py`, FUS-04)

| 받아쓴 문장 | 긴급 정지? | 이유 |
|---|---|---|
| "자비스 멈춰", "자비스 긴급 정지" | 예 | 호출어 + 긴급어 (긴급·비상·정지·멈춰·그만·스톱) |
| "자비스 타이머 정지", "자비스 알람 그만" | 아니오 | 타이머 이야기 → 명령 해석이 타이머 취소로 처리 |
| "멈춰!", "그만 그만" | 예 | 호출어가 없어도 문장 전체가 짧은 긴급 표현이면 (다급할 때) |
| "그만 먹을래", "자비스 지금 위험해?" | 아니오 | 대화 속 긴급어 / 위험 확인 |

- 명령 해석(llm_svc)도 같은 말을 `EMERGENCY_STOP`으로 낸다. 빠른 경로로 정지한 뒤 3초 안에 온 `EMERGENCY_STOP`은 같은 요청으로 보고 다시 실행하지 않는다.

## 제어 명령 (`control/command`)

| 허용된 명령 | `cmd` | `target` | `value` |
|---|---|---|---|
| `TURN_ON` | `TURN_ON` | 장치 | 1 (켤 때 세기 1, interfaces §2.2) |
| `SET_LEVEL` | `SET_LEVEL` | 장치 | 1~3 |
| `TURN_OFF` | `TURN_OFF` | 장치 또는 `all` | 0 |
| `EMERGENCY_STOP` | `EMERGENCY_STOP` | `all` | 0 |

- `seq`는 1부터 하나씩 늘어난다 (서비스를 다시 띄우면 1부터). `session_id`는 받은 명령의 것을 이어 쓴다 (지연 분해, `bench/latency.py`).
- 타이머·상태 확인·되묻기·지원 외는 판정만 하고 장치로 보내지 않는다. **타이머 실행(끝나면 장치 끄기)은 v0에 없다.**

## Spec

| 항목 | 내용 |
|---|---|
| 입력 | `llm/function_call`, `fusion/state`, `stt/text` |
| 출력 | `guard/decision` (명령마다), `control/command` (허용된 제어만), `system/heartbeat` (1초) |
| 설정 | `--bus`, `--session`, `--assume-state`(개발용), `--quiet` |
| 자원 | CPU 무시할 수준 (규칙 판정 1건 1ms 미만) |
| 실패 시 | 상태 입력이 없으면 화구 켜기·세기 거부. 형식이 틀린 명령은 거부. 이 서비스가 죽으면 제어 명령이 나가지 않는다 (장치는 그대로) — 가열 장치의 최종 안전은 가상 주방 쪽 안전장치(L0, HW-18)가 맡는다 |
| 하지 않는 일 | 과열·방치 자동 차단(FUS-09), 결제 확인(`ASK`, 스키마 v0.2), 타이머 실행 |

## 확인 기록

| 날짜 | 장소 | 확인한 것 |
|---|---|---|
| 2026-10-05 | Windows PC, `memory://` | 단위 테스트: 판정 규칙, 긴급어, 서비스 발행·중복 정지 무시, llm_svc와 이은 "후드 켜 줘" → `control/command`. MQTT·보드는 미검증 (이 PC에 브로커 없음) |
