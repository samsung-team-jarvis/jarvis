# Recipe: 소형 LLM LoRA 학습 → RKLLM(W8A8) 변환 → 보드 추론

> ⚠️ **검증 전 초안.** BOARD-05, BOARD-06, LLM-07, LLM-08을 진행하면서 실제 명령으로 교체한다. 기준은 airockchip/rknn-llm 저장소다.

## 개념 3줄

- **LoRA**: 모델 전체가 아니라 작은 추가 가중치만 학습하는 방법. Colab GPU로도 가능하다.
- **병합(merge)**: 학습한 LoRA 가중치를 원래 모델에 합쳐 fp16 모델 하나로 만든다. RKLLM은 이 병합 모델을 변환한다.
- **chat template / eos**: 모델이 대화를 인식하는 형식과 "여기서 끝" 신호. 학습·변환·보드 추론에서 **완전히 같아야** 한다. 어긋나면 정답 뒤에 쓸데없는 문장을 계속 생성한다.

## 0. 모델 선택

- RKLLM **지원 모델 목록**에 있는 모델만 후보로 한다 (rknn-llm README).
- 후보와 선택 근거는 decision log로 남긴다 (open-questions Q-07).

## 1. LoRA 학습 (Colab GPU)

- 데이터: `train.jsonl` ([interfaces](../docs/architecture/interfaces.md) §3.1 형식)
- 도구: PEFT 또는 Unsloth (결정 후 기록)
- 고정할 것: chat template, system prompt, eos 토큰, 최대 길이 → 실험 spec에 기록

## 2. fp16 병합

LoRA 어댑터를 base 모델에 병합해 Hugging Face 형식 디렉터리로 저장.

## 3. RKLLM 변환 (x86_64 Linux — Colab)

```python
from rkllm.api import RKLLM

llm = RKLLM()
llm.load_huggingface(model="./merged_fp16")
llm.build(do_quantization=True, quantized_dtype="w8a8", target_platform="rk3588",
          dataset="calib.json")                          # 캘리브레이션: Train 발화에서만
llm.export_rkllm("./jarvis_w8a8.rkllm")
```

(함수 이름·인자는 사용하는 rkllm-toolkit 버전 예제로 확인 필요)

## 4. 보드 추론

- rknn-llm 저장소의 데모(C++)로 먼저 동작을 확인한다.
- 서비스(`llm_svc`)에서는 런타임 C API를 Python에서 호출하거나 데모를 감싸는 방식 중 선택 (결정 후 기록).
- 최대 context 길이, 생성 토큰 수, greedy decoding 설정을 고정한다.

## 5. 측정 (experiment-workflow)

- 3단계 비교: ① 기본 모델(서버) ② 학습 모델(서버 fp16) ③ 양자화 모델(보드 .rkllm) — 같은 문항·템플릿·greedy
- 지표: Action Accuracy, Entity Accuracy, JSON Valid Rate, Unsafe Action Rate, tok/s, TTFT, RAM
- 규칙 파서 결과와 같은 표에 놓고 비교
