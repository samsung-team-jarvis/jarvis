# Decision: Function Call 스키마 v0.1 (장치·세기·타이머·함수 토큰 문법)

## Status
- 2026-10-05 [가상 주방 결정](./2026-10-05-virtual-kitchen-demo.md)으로 장치를 8종으로 넓히기로 했다 → [스키마 v0.2](./2026-10-06-function-call-schema-v02.md)에서 target·Action을 추가했다 (LLM-13). 아래는 v0.1 결정 기록이다.
- Accepted

## Date
- 2026-10-02

## Context
- 규칙 파서(FUS-02), Safety Guard(FUS-03), LLM 데이터(LLM-02~05), STT 녹음 대본(STT-05), BLE 코드표(HW-01)가 모두 명령 형식을 기다렸다. 초안에는 target 후보·세기 범위·타이머 동작·LLM 출력 문법이 비어 있었다 (#39).
- LLM 출력은 SUDA식 함수 토큰으로 하기로 이미 정했다 ([Q-10](./open-questions.md)). 소형 LLM(1B급)은 출력 토큰이 짧을수록 빠르고, 산수·긴 문장 생성에 약하다.
- 제어 대상은 실물이 아니라 저전압 모형이다 ([안전 3계층](./2026-10-01-safety-layers.md)). 모형과 target이 1:1로 맞아야 시연이 된다.
- 결정권자(이현종)가 정하고 팀에 통보한다. FUS-01(State)은 담당(최지환)이 상황 인식을 구현하며 바꿀 수 있다.

## Options
- 장치: (A) 후드 + 화구 2 + 전체 / (B) A + 튀김기 / (C) 후드 + 화구 1 + 전체
- 세기: (A) 후드·화구 모두 1~3 / (B) 후드만 1~3 / (C) 세기 조절 없음
- 타이머 종료 동작: (A) 대상이 있으면 끄기, 없으면 알림 / (B) 알림만 / (C) 끄기만(대상 필수)
- 빠진 정보 표현: (A) LLM이 `ASK_CLARIFY(question="…")`로 질문 문장 생성 / (B) 하려던 Action에 `?`를 넣고 질문은 템플릿(SUDA의 -1 방식)
- 시간 표현: (A) LLM이 `duration_s`(초) 출력 / (B) LLM은 `min`·`sec`, 초 환산은 코드
- 확인 필요 여부: (A) LLM이 `need_confirmation` 출력 / (B) Safety Guard가 상태를 보고 `ASK` 판정

## Decision
- 장치 **A** (`hood`, `burner_1`, `burner_2`, `all`): 튀김기는 화구 위에서 쓰는 것으로 본다. 모형·학습 데이터가 단순하고, "2번 화구" 같은 번호 인식은 시연에 남는다.
- 세기 **A** (1~3, 약·중·강): "후드 세게", "불 약하게" 둘 다 자연스러운 명령이다. 모형은 PWM(팬 속도·LED 밝기)으로 표현.
- 타이머 **A**: "3분 뒤 1번 화구 꺼 줘"(자동 끄기)와 "타이머 3분"(알림)을 모두 지원. 장치당 1개, 최대 60분.
- 빠진 정보 **B**: 질문 문장을 생성하면 출력 토큰이 길어지고 틀릴 수 있다. `?`는 토큰 1~2개이고, 질문은 `missing`별 고정 문장으로 TTS가 읽는다.
- 시간 **B**: "3분 30초" → `min=3, sec=30`. 곱셈을 모델에 맡기지 않는다.
- 확인 필요 **B**: 위험 여부는 현재 State·센서를 아는 Guard가 판단한다 (LLM은 명령 해석만).
- `TURN_ON all`은 허용하지 않는다 (한 번에 모두 켤 이유가 없고 위험).
- State는 초안(`IDLE, PREHEAT, COOKING, UNATTENDED, DANGER, SAFE_STOP`)으로 확정한다.

## Consequences
- 장점: 파서·Guard·데이터 검증이 같은 코드([`common/function_call.py`](../../common/function_call.py))를 쓴다. LLM 출력이 짧다.
- 단점: 상대 조절("조금 더")·튀김기 별도 제어는 v0에서 못 한다. 되묻기 후 다음 발화를 이어 받는 대화 흐름은 따로 만들어야 한다.
- 영향: [interfaces](../architecture/interfaces.md) §2.2·§2.3·§3, PLAN FUS-02·FUS-03·FUS-04, LLM-02~05(데이터는 이 스키마로), STT-05(녹음 대본), HW-01(target·level 코드표, PWM 세기), STT-12(되묻기·응답 문장)

## Verification
- 스키마 규칙과 interfaces §3.3 예시 표를 `tests/common/test_function_call.py`가 검사한다 (문서 표를 직접 읽음).
- 함수 토큰 형식이 실제로 생성 지연을 줄이는지는 LLM Baseline(Phase 3)에서 측정한다 — 미측정.

## Revisit
- 모형에 튀김기 등 장치가 추가되면 target 추가 (번호·이름은 기존 것을 바꾸지 않고 덧붙인다)
- LLM이 `?` 형식을 잘 학습하지 못하면(되묻기 정확도가 낮으면) ASK_CLARIFY 표현 재검토
- 상대 조절 요청이 테스트 세트에서 자주 나오면 `level_delta` 등 추가 검토
