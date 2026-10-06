# Decision: 학습한 LLM의 입력 형식 (짧은 지시문 · chat template · 끝 토큰)

## Status
- Accepted (LLM-07, #88)

## Date
- 2026-10-06

## Context
- 학습·평가·양자화 캘리브레이션·보드 추론이 **글자 하나까지 같은 입력**을 써야 한다. 다르면 학습한 것이 보드에서 나오지 않는다 ([recipe](../../recipes/llm-to-rkllm.md) "chat template / eos").
- 기본 모델 기준선(LLM-06)은 함수 14개를 설명하는 긴 지시문 + 예시 17개로 쟀다. 이 입력을 그대로 학습에 쓰면 문장마다 수백 토큰이 붙는다.
  - 2026-10-05 Mac 시험 학습(저장소 밖)에서 긴 지시문(387토큰)은 16GB 메모리로 학습이 멈췄고, 한 줄 지시문(문장당 평균 84토큰)은 22분에 끝났다.
  - 보드에서는 입력이 길수록 첫 토큰이 늦게 나온다 (명령마다 지시문 전체를 다시 읽는다).
- interfaces §3.2는 함수 토큰(`<jarvis_N>`, `<jarvis_end>`)을 토크나이저의 특수 토큰으로 넣을지 "학습 단계에서 정한다"고 남겨 두었다.

## Options
- 지시문: (A) 짧은 한 줄 + 예시 없음 — 함수 설명은 데이터로 배운다 / (B) 기준선과 같은 긴 지시문 + 예시
- 함수 토큰: (A) 보통 글자로 둔다 (기존 토큰으로 쪼개짐) / (B) 특수 토큰으로 추가한다
- 끝 토큰: (A) 모델의 대화 끝 토큰(Qwen3는 `<|im_end|>`) / (B) `<jarvis_end>`

## Decision
- 선택한 안: 모두 **A** (결정: 이현종)

| 항목 | 값 |
|---|---|
| system | `가게 음성 명령을 함수 토큰 한 줄로 바꾼다.` ([`services/llm_svc/prompt.py`](../../services/llm_svc/prompt.py) `FINETUNED_SYSTEM_PROMPT`) |
| user | `상황: state={State}, 마지막 장치={last_target 또는 없음}\n말: {호출어를 뺀 명령}` (같은 파일 `user_message`) |
| 예시(few-shot) | 없음 |
| chat template | 베이스 모델에 들어 있는 것을 그대로 쓴다. Qwen3는 생각 모드를 끈다(`enable_thinking=False`) — assistant 시작 뒤에 빈 `<think>\n\n</think>\n\n`이 붙는다 |
| 정답 | 함수 토큰 + 끝 토큰. 예: `<jarvis_1>(target=burner_1)<jarvis_end><\|im_end\|>`. loss는 정답 부분에만 건다 |
| 끝 토큰 | 모델의 대화 끝 토큰 (Qwen3: `<\|im_end\|>`, id 151645). `llm_svc`는 `<jarvis_end>`까지만 읽으므로 뒤에 무엇이 붙어도 파싱은 같다 |
| 함수 토큰 | 특수 토큰으로 추가하지 않는다 |

Qwen3-0.6B에 적용한 실제 입력 (`train_log.json`의 `prompt_example`):

```text
<|im_start|>system
가게 음성 명령을 함수 토큰 한 줄로 바꾼다.<|im_end|>
<|im_start|>user
상황: state=COOKING, 마지막 장치=없음
말: 일번 화구 켜줘<|im_end|>
<|im_start|>assistant
<think>

</think>

```

- 선택 이유:
  - 짧은 입력: Mac에서 학습할 수 있고, 보드에서 첫 토큰이 빨리 나온다. 함수 목록은 학습 데이터(14개 Action이 모두 들어 있음)로 배운다.
  - 특수 토큰을 넣지 않음: 토큰을 추가하면 어휘 크기와 임베딩 행렬이 바뀌어 새 임베딩을 처음부터 배워야 하고, RKLLM 변환에서 확인할 것이 늘어난다. 2026-10-05 시험 학습에서 보통 글자로도 형식을 지켰다 (v1 test 형식 통과 88.4%, 저장소 밖 실험).
  - 모델의 끝 토큰: 베이스 모델이 이미 대화 끝에서 멈추도록 배워 있고, 보드 데모·서버도 이 토큰으로 생성을 멈춘다.

## Consequences
- 장점: 학습한 모델의 입력이 짧다 (Qwen3-0.6B 기준 정답 포함 평균 84토큰, 최대 112).
- 단점: 학습하지 않은 기본 모델과 입력이 달라, "기본 모델+긴 지시문"과 "학습 모델+짧은 지시문"을 비교하게 된다 (LLM-06 기준선과 LLM-07은 설정이 다르다는 것을 METRICS에 적는다).
- 지시문·사용자 메시지 형식을 바꾸면 다시 학습해야 한다.
- 영향: [`training/llm/train_lora.py`](../../training/llm/train_lora.py), [`bench/llm_eval.py`](../../bench/llm_eval.py) `--finetuned`, LLM-08 변환 설정(`system_prompt`, `prompt_template`, `calib_stop_at`), LLM-09 `llm_svc`

## Verification
- `tests/training/test_train_lora.py`: 입력에 짧은 지시문·사용자 메시지가 들어가고, loss가 정답과 끝 토큰에만 걸린다
- 학습 → 병합 저장 → 다시 불러와 `bench/llm_eval.py --finetuned`로 평가 (Mac, 2026-10-06)

## Revisit
- 학습한 모델의 형식 통과율(Valid Rate)이 낮을 때 — 함수 토큰을 특수 토큰으로 넣는 것을 다시 본다
- 다른 베이스 모델(Llama-3.2-1B 등)을 쓸 때 — chat template과 끝 토큰이 그 모델 것으로 바뀐다
- RKLLM 변환에서 chat template을 그대로 옮길 수 없을 때 (LLM-08)
