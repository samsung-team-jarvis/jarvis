# llm_svc — 명령 해석 (stt/text → Function Call)

호출어가 있는 발화(`stt/text`, `wake: true`)를 명령([interfaces](../../docs/architecture/interfaces.md) §3, 스키마 v0.2)으로 바꿔 `llm/function_call`로 발행한다. 기본은 규칙 파서만 쓴다 (PLAN FUS-02). LLM(`--model`)을 붙이면 LLM 출력을 먼저 쓰고, **출력이 검증에 실패하면 규칙 파서로 대체**한다 (LLM-09, [decision](../../docs/decisions/2026-10-01-rule-parser-baseline.md)).

```text
stt/text (wake=true)  ─▶ 호출어 떼기 ─▶ STT 오인식 사전 ─┬▶ 규칙 파서 ───────────────────────────▶ llm/function_call
                         "자비스 후드 켜 줘."  →  "후드 켜 줘." │                                        ▲
                                                           └▶ LLM ─▶ 검증(parse_tokens) ─ 통과 ──────┤
                                                                                       └ 실패 → 규칙 파서
stt/text (wake=false) ─▶ 무시 (개수만 셈)
```

해석 경로(호출어 → 사전 → LLM → 규칙 파서)는 `interpret.py` 하나이고, 측정(`bench.stt_eval`, `bench.llm_fallback`)도 같은 함수를 쓴다.

## 실행

```bash
python -m services.llm_svc                          # 규칙 파서만. 버스는 JARVIS_BUS (기본 MQTT)
python -m services.llm_svc parse "3분 뒤에 2번 불 꺼"  # 버스 없이 결과만 (JSON + 함수 토큰)
# 학습한 LLM + 검증 실패 시 규칙 파서 (.venv-llm). 실행용은 GGUF(llama.cpp CPU, LLM-18), HF 폴더는 Mac 비교용
.venv-llm/bin/python -m services.llm_svc --model runs/llm/llm_qwen3-0.6b_jarvis_v4-q8_0.gguf
.venv-llm/bin/python -m services.llm_svc --model runs/llm/llm_qwen3-0.6b_jarvis_v4
.venv-llm/bin/python -m services.llm_svc --model runs/llm/llm_qwen3-0.6b_jarvis_v4 parse "일번 화구 약하게"
```

MQTT 확인 (Mac, 2026-10-16, #114): 브로커(`eclipse-mosquitto:2`) 위에서 `--model runs/llm/llm_qwen3-0.6b_jarvis_v4`로 띄우고 `fusion/state`(COOKING) 뒤 `stt/text` 5건을 보냈다. 일번 화구 켜기·후드 세게·타이머 3분은 LLM 출력이 그대로 통과해 맞게 발행됐고(`gen_ms` 첫 문장 872 ms, 그 뒤 407·335 ms), "자비스."만 말한 경우는 LLM 없이 되묻기, 호출어 없는 발화는 무시됐다. SIGTERM으로 3초 안에 종료.

생성기는 `interpret.Generate`(명령 문장·context → LLM 출력·토큰 수) 자리에 바꿔 끼운다: `gguf_engine.GGUFGenerator`(llama.cpp CPU, 실행용 — RKLLM 대신, [decision](../../docs/decisions/2026-10-29-llamacpp-and-rebalance.md)), `hf_engine.HFGenerator`(Mac 비교용). GGUF 생성기는 tokenizer 없이 학습과 같은 입력 문자열(`prompt.chat_prompt`)을 만든다. GGUF 만들기: `bash training/convert/hf_to_gguf.sh <모델 폴더> q8_0`. Mac CPU 4스레드에서 v4 q8_0 test 87.1% / 86.7%(HF fp16과 같은 수준), 287 ms/건 ([METRICS](../../docs/METRICS.md)).

음성부터 명령까지 한 번에 (브로커 필요 — [local-development](../../docs/workflows/local-development.md)):

```bash
python3 scripts/launch.py                                           # recorder → kitchen_gw → safety_guard → llm_svc → audio_svc(마이크)
```

## 발행 내용

| 필드 | 규칙 파서만 | LLM 출력이 통과 | LLM 출력이 검증 실패 → 규칙 파서 |
|---|---|---|---|
| `call` | 규칙 파서 결과 | LLM 결과 | 규칙 파서 결과 |
| `raw_text` | 파서에 넣은 명령 문장 | LLM 출력 (함수 토큰) | 파서에 넣은 명령 문장 |
| `valid` | `true` | `true` | `false` |
| `fallback` | `true` | `false` | `true` |
| `gen_ms` | 파싱 시간 | LLM 생성 + 검증 시간 | LLM 생성 + 검증 + 파싱 시간 |
| `tokens` | `0` | LLM 생성 토큰 수 | LLM 생성 토큰 수 (버려도 쓴 만큼) |

- `call`은 어느 경우든 `common.function_call.validate`를 통과한다. 검증은 형식·함수 번호·장치 이름·꼭 필요한 인자·값 범위(세기 1~3, 타이머 1~3600초)를 본다. 검증은 통과했지만 뜻이 틀린 명령은 그대로 나간다 — 안전은 Safety Guard가 맡는다.
- LLM 입력은 학습과 같게 만든다: 문장부호를 빼고(학습 문장에 없다), 상황은 `fusion/state`의 마지막 상태(받은 적이 없으면 `IDLE`), `last_target`은 이 서비스가 마지막으로 발행한 명령의 장치(`all` 제외, 60초 지나면 없음 — "그거 꺼 줘", LLM-12). 호출어만 말한 경우는 LLM에 넣지 않는다.

`session_id`는 받은 `stt/text`의 것을 그대로 쓴다 (발화 → 명령 지연을 같은 세션에서 추적). `system/heartbeat`는 1초마다 자기 세션(`--session`)으로 발행한다.

### 대체 효과 (Mac 참고값, 2026-10-13)

LoRA v4가 이미 낸 출력(`bench/llm_eval.py --csv`)에 같은 함수를 적용해 쟀다 (`bench/llm_fallback.py` — 모델을 다시 돌리지 않음). 데이터 v2 test (n=474):

| | Action Acc | Entity Acc | 틀린 수 | 규칙 위반 | 틀린 실행 |
|---|---|---|---|---|---|
| 규칙 파서만 | 82.5% | 82.1% | 85 | 0 | 13 |
| LoRA v4만 | 86.9% | 86.5% | 64 | 12 | 11 |
| **LoRA v4 + 규칙 파서 대체** | **89.2%** | **88.8%** | **53** | **0** | 11 |

- 검증에 실패한 12건(2.5%)을 규칙 파서로 바꿨고, 그중 11건이 맞았다. 틀린 실행은 그대로다 (검증을 통과한 오류는 대체하지 않는다).
- val(n=508)은 v4 출력이 모두 통과해 대체 0건, 98.8% 그대로.
- 대체 정책은 2026-10-01 결정대로이고 test를 보고 고르지 않았다. test 오류는 건수만 셌다 (`--counts-only`).

## 규칙 파서 (`rule_parser.py`)

문장을 띄어쓰기·문장부호 없이 이어 붙인 뒤 키워드로 판단한다. 판단 순서와 키워드는 코드 상단에 모아 두었다.

| 순서 | 판단 | 예 |
|---|---|---|
| 1 | 빈 문장(호출어만) → 의도 불명 되묻기 | "자비스." |
| 2 | "네"·"아니요"만 말함 → `CONFIRM` / `DENY` | "네", "취소" |
| 3 | 긴급어(긴급·비상·정지·멈춰·그만) → `EMERGENCY_STOP` — 타이머 이야기가 아닐 때만. 조명·에어컨·선풍기·음악을 멈추라는 말이면 그 장치 끄기 | "멈춰" (단, "타이머 정지"는 타이머 끄기, "음악 멈춰"는 음악 끄기) |
| 4 | 결제 → `CHECK_AMOUNT`(금액을 물음) / `REQUEST_PAYMENT` / 취소면 `DENY` | "얼마야?", "결제해 줘", "결제 취소" |
| 5 | 타이머 → `CANCEL_TIMER` / `SET_TIMER` / 시간 되묻기 | "타이머 삼 분 삼십 초", "3분 뒤에 1번 화구 꺼 줘" |
| 6 | 위험 확인 → `CHECK_RISK` | "지금 위험해?" |
| 7 | 상태 확인 → `CHECK_STATUS` ("어때·확인"은 장치 이름과 같이 나올 때만) | "1번 화구 켜져 있어?" |
| 8 | 세기 → `SET_LEVEL` (약·중·강, 어둡게·밝게, 작게·크게, N단; "더·줄여" 같은 상대 조절은 되묻기) | "후드 세게", "조명 어둡게", "소리 크게" |
| 9 | 켜기·끄기 → `TURN_ON` / `TURN_OFF` | "환풍기 틀어 줘", "노래 틀어 줘", "다 꺼 줘" |
| 10 | 장치만 → 의도 불명 되묻기, 그 외 → `UNSUPPORTED` | "후드", "오늘 날씨 어때?" |

- 장치: 후드·환풍기 → `hood`, "1번/첫 번째 화구·불·버너" → `burner_1`, 2번 → `burner_2`, 튀김기 → `fryer`, 조명·전등·불빛 → `light`, 에어컨 → `aircon`, 선풍기 → `fan`, 음악·노래·볼륨·소리 → `music`, 전부·모두·"다 꺼" → `all`. 번호 없는 화구·없는 번호는 장치 되묻기.
- 결제: "결제"가 들어가거나 문장이 "계산"으로 시작할 때만 ("칼로리 계산해 줘"는 지원 외). 타이머는 가열 장치·후드에만 — "에어컨 10분 뒤에 꺼 줘"는 지원 외.
- 시간: 아라비아 숫자, 한자어 수(삼, 이십오), 고유어 수(열다섯, 스무), "1분 반".
- "화국"은 SenseVoice가 "화구"를 받아쓴 실제 출력이라 화구로 본다 ([audio_svc](../audio_svc/README.md)).
- **한계**: 모르는 대상 + 켜기 동사("커피 머신 켜 줘")는 장치를 되묻는다. 이런 사례가 LLM과의 비교 지점이다 (FUS-06).

발화별 기대 결과는 `tests/llm_svc/test_rule_parser.py`에 있다. 규칙을 바꾸면 이 표를 같이 고친다.

## STT 오인식 사전 (`stt_fixes.py`, STT-10)

파서에 넣기 전에 SenseVoice가 자주 틀리는 표현을 고친다. `stt/text`에는 원문이 그대로 남고, 고친 문장이 `raw_text`로 남는다. 측정(`bench.stt_eval`)도 같은 경로(`interpret.py`: 호출어 → 사전 → 파서)를 쓴다.

| 틀린 표현 | 고친 표현 | 원래 말 |
|---|---|---|
| 타임머 | 타이머 | 타이머 |
| 세개 | 세게 | 세게 |
| 세 개 해 | 세게 해 | 세게 해 (#128) |
| 번구 | 번 화구 | 1번 화구 → "일 번구" |
| 일본 번 / 일본 | 일번 / 1번 | 1번 화구 → "일본 번 화국" |

**숫자 정규화** (`numerals`, #130): 받아쓰기는 "1번"을 "일 번", "2번"을 "입 번", "10분"을 "십 분"으로 낸다. 한자어 숫자 + 단위를 아라비아 숫자로 바꾼다 — 번은 장치(화구·불·버너) 앞에서만("이번에"는 그대로), 단은 "으로"·"계" 앞이나 끝에서만("일단 후드 켜"는 그대로). 사전과 달리 **서비스 입력(`command_text`)에만** 쓰고 학습 데이터 생성에는 쓰지 않는다. spk01 val을 서비스 경로로 돌리면 음성 → 명령 전체 일치 25/34 → 28/34 (GGUF LLM), 글로 된 val 문장 중 바뀌는 39개는 전후 모두 39/39.

- **근거는 val 화자에서만 찾는다** (지금은 spk01 1명, MacBook 마이크 30cm). test 화자를 보고 고치지 않는다.
- "입(2번)", "하고(화구)", "산(3)"처럼 흔한 말로 틀리는 경우는 넣지 않았다 — 다른 문장을 망칠 수 있다.
- 효과 (spk01 val 40문장, 같은 녹음): STT→Action 70.6% → **88.2%**, 호출어 인식 91.2% → 97.1% (호출어 형태 추가 포함), 오호출 0% 유지. **한 명 기준이라 test 화자로 다시 확인해야 한다.**
