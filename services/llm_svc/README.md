# llm_svc — 명령 해석 (stt/text → Function Call)

호출어가 있는 발화(`stt/text`, `wake: true`)를 명령([interfaces](../../docs/architecture/interfaces.md) §3)으로 바꿔 `llm/function_call`로 발행한다. **v0는 규칙 파서만** 있다 (PLAN FUS-02). LLM 연결은 LLM-09에서 붙이고, 그때 규칙 파서는 LLM 출력 검증이 실패할 때의 대체 경로이자 비교 기준선이 된다 ([decision](../../docs/decisions/2026-10-01-rule-parser-baseline.md)).

```text
stt/text (wake=true)  ─▶ 호출어 떼기 ─▶ STT 오인식 사전 ─▶ 규칙 파서 ─▶ llm/function_call
                         "자비스 후드 켜 줘."  →  "후드 켜 줘."  →  {"action":"TURN_ON","target":"hood"}
stt/text (wake=false) ─▶ 무시 (개수만 셈)
```

해석 경로(호출어 → 사전 → 파서)는 `interpret.py` 하나이고, 측정(`bench.stt_eval`)도 같은 함수를 쓴다.

## 실행

```bash
python -m services.llm_svc                          # 버스는 JARVIS_BUS (기본 MQTT)
python -m services.llm_svc parse "3분 뒤에 2번 불 꺼"  # 버스 없이 결과만 (JSON + 함수 토큰)
```

음성부터 명령까지 한 번에 (브로커 필요 — [local-development](../../docs/workflows/local-development.md)):

```bash
python3 scripts/launch.py                                           # recorder → kitchen_gw → llm_svc → audio_svc(마이크)
```

## 발행 내용 (규칙 파서일 때)

| 필드 | 값 |
|---|---|
| `call` | Function Call JSON (`common.function_call.validate` 통과 보장) |
| `raw_text` | 파서에 넣은 명령 문장 (호출어를 뺀 부분) |
| `valid` | `true` |
| `fallback` | `true` — 규칙 파서가 만든 명령 |
| `gen_ms` | 파싱 시간 (ms) |
| `tokens` | `0` |

`session_id`는 받은 `stt/text`의 것을 그대로 쓴다 (발화 → 명령 지연을 같은 세션에서 추적). `system/heartbeat`는 1초마다 자기 세션(`--session`)으로 발행한다.

## 규칙 파서 (`rule_parser.py`)

문장을 띄어쓰기·문장부호 없이 이어 붙인 뒤 키워드로 판단한다. 판단 순서와 키워드는 코드 상단에 모아 두었다.

| 순서 | 판단 | 예 |
|---|---|---|
| 1 | 빈 문장(호출어만) → 의도 불명 되묻기 | "자비스." |
| 2 | 긴급어(긴급·비상·정지·멈춰·그만) → `EMERGENCY_STOP` — 타이머 이야기가 아닐 때만 | "멈춰" (단, "타이머 정지"는 타이머 끄기) |
| 3 | 타이머 → `CANCEL_TIMER` / `SET_TIMER` / 시간 되묻기 | "타이머 삼 분 삼십 초", "3분 뒤에 1번 화구 꺼 줘" |
| 4 | 위험 확인 → `CHECK_RISK` | "지금 위험해?" |
| 5 | 상태 확인 → `CHECK_STATUS` ("어때·확인"은 장치 이름과 같이 나올 때만) | "1번 화구 켜져 있어?" |
| 6 | 세기 → `SET_LEVEL` (약·중·강, N단; "더·줄여" 같은 상대 조절은 되묻기) | "후드 세게", "후드 2단" |
| 7 | 켜기·끄기 → `TURN_ON` / `TURN_OFF` | "환풍기 틀어 줘", "다 꺼 줘" |
| 8 | 장치만 → 의도 불명 되묻기, 그 외 → `UNSUPPORTED` | "후드", "오늘 날씨 어때?" |

- 장치: 후드·환풍기 → `hood`, "1번/첫 번째 화구·불·버너" → `burner_1`, 2번 → `burner_2`, 전부·모두·"다 꺼" → `all`. 번호 없는 화구·없는 번호는 장치 되묻기.
- 시간: 아라비아 숫자, 한자어 수(삼, 이십오), 고유어 수(열다섯, 스무), "1분 반".
- "화국"은 SenseVoice가 "화구"를 받아쓴 실제 출력이라 화구로 본다 ([audio_svc](../audio_svc/README.md)).
- **v0 한계**: 모르는 대상 + 켜기 동사("노래 틀어 줘")는 장치를 되묻는다. 이런 사례가 LLM과의 비교 지점이다 (FUS-06).

발화별 기대 결과는 `tests/llm_svc/test_rule_parser.py`에 있다. 규칙을 바꾸면 이 표를 같이 고친다.

## STT 오인식 사전 (`stt_fixes.py`, STT-10)

파서에 넣기 전에 SenseVoice가 자주 틀리는 표현을 고친다. `stt/text`에는 원문이 그대로 남고, 고친 문장이 `raw_text`로 남는다. 측정(`bench.stt_eval`)도 같은 경로(`interpret.py`: 호출어 → 사전 → 파서)를 쓴다.

| 틀린 표현 | 고친 표현 | 원래 말 |
|---|---|---|
| 타임머 | 타이머 | 타이머 |
| 세개 | 세게 | 세게 |
| 번구 | 번 화구 | 1번 화구 → "일 번구" |
| 일본 번 / 일본 | 일번 / 1번 | 1번 화구 → "일본 번 화국" |

- **근거는 val 화자에서만 찾는다** (지금은 spk01 1명, MacBook 마이크 30cm). test 화자를 보고 고치지 않는다.
- "입(2번)", "하고(화구)", "산(3)"처럼 흔한 말로 틀리는 경우는 넣지 않았다 — 다른 문장을 망칠 수 있다.
- 효과 (spk01 val 40문장, 같은 녹음): STT→Action 70.6% → **88.2%**, 호출어 인식 91.2% → 97.1% (호출어 형태 추가 포함), 오호출 0% 유지. **한 명 기준이라 test 화자로 다시 확인해야 한다.**
