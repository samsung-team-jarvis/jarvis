# Recipe: 소형 LLM LoRA 학습 → RKLLM(W8A8) 변환 → 보드 추론

> 2026-10-02 공식 저장소·SDK 문서(RKLLM 1.3.1)로 절차를 확인했다 (아래 출처). 실제 실행 결과(BOARD-05·06, LLM-07·08)는 아직 없다.

## 개념 3줄

- **LoRA**: 모델 전체가 아니라 작은 추가 가중치만 학습하는 방법. Colab GPU로도 가능하다.
- **양자화(W8A8)**: 가중치·활성값을 8비트로. RK3588에서 RKLLM이 지원하는 방식이다.
- **chat template / eos**: 모델이 대화를 인식하는 형식과 "여기서 끝" 신호. 학습·변환·보드 추론에서 **완전히 같아야** 한다. 어긋나면 정답 뒤에 쓸데없는 문장을 계속 생성한다.

## 확인된 제약 (RKLLM 1.3.1, 2026-09-29 릴리스)

| 항목 | 내용 |
|---|---|
| 변환 도구 실행 환경 | **Linux x86_64 전용**, Python 3.10~3.12 → Mac 불가, Colab 사용 |
| RK3588 양자화 타입 | `w8a8`, `w8a8_g128`, `w8a8_g256`, `w8a8_g512` (w4a16은 RK3588 미지원) |
| 최소 NPU 드라이버 | **v0.9.8** (보드에서 `sudo cat /sys/kernel/debug/rknpu/version`) |
| 보드 런타임 | C/C++ API (`librkllmrt`). Python에서 쓰려면 ctypes 래퍼 또는 데모 프로세스를 감싼다 |
| LoRA | 지원. LoRA를 별도 `.rkllm`으로 변환해 런타임에 불러올 수 있다 (`rkllm_load_lora`) |
| max_context | 32의 배수, 최대 16384 |

## 0. 모델 선택

- README의 지원 계열: LLaMA, TinyLLaMA, Qwen2/2.5/3/3.5, Gemma/2/3/3n/4 등.
- RK3588 공식 벤치마크에 있는 소형 모델: Qwen2-0.5B, Qwen2.5-1.5B, Qwen3-0.6B, TinyLLaMA-1.1B.
- Llama-3.2-1B, Qwen2.5-0.5B는 계열(LLaMA, Qwen2.5)로는 지원되지만 **이름으로 명시된 목록은 확인하지 못했다** → 변환을 실제로 해봐야 확정 (LLM-06).
- 후보와 선택 근거는 decision log로 남긴다 ([open-questions](../docs/decisions/open-questions.md) Q-07).

## 1. LoRA 학습 (Colab GPU)

- 데이터: `train.jsonl` ([interfaces](../docs/architecture/interfaces.md) §3.1 형식)
- 도구: PEFT 또는 Unsloth (결정 후 기록)
- 고정할 것: chat template, system prompt, eos 토큰, 최대 길이 → 실험 spec에 기록

## 2. 변환 방식 선택

| 방식 | 방법 | 장단점 |
|---|---|---|
| 병합 | LoRA를 base에 병합해 fp16 HF 모델로 저장 → 변환 | 파일 1개, 단순 |
| 분리 | base는 그대로 변환, LoRA는 `model_lora=`로 따로 변환 → 런타임에 로드 | LoRA만 바꿔 실험 가능 (데이터 개선 사이클이 빠름) |

## 3. RKLLM 변환 (Colab, x86_64)

Colab 노트북: [`training/colab/convert_rkllm.ipynb`](../training/colab/convert_rkllm.ipynb). rknn-toolkit2와 의존성이 충돌하므로 **별도 런타임**에서 실행한다 (torch 2.6.0 vs ≤ 2.2.0).


공식 예제(`examples/rkllm_api_demo/export/export_rkllm.py`, release-v1.3.1) 기준. 값의 대소문자도 예제 그대로 쓴다 (`RK3588`, `W8A8`). 스크립트: [`training/convert/hf_to_rkllm.py`](../training/convert/hf_to_rkllm.py)

```python
from rkllm.api import RKLLM

llm = RKLLM()
llm.load_huggingface(model="./merged_fp16", model_lora=None, device="cuda", dtype="float32")
llm.build(
    do_quantization=True,
    optimization_level=1,
    quantized_dtype="W8A8",
    quantized_algorithm="normal",
    target_platform="RK3588",
    num_npu_core=3,          # YOLO와 NPU를 나눠 쓸 경우 조정 (architecture §6, BOARD-08)
    dataset="./quant.json",  # 캘리브레이션: Train 발화에서만
    hybrid_rate=0,
    max_context=4096,
)
llm.export_rkllm("./jarvis_w8a8.rkllm")
```

`quant.json`: `[{"input": "...", "target": "..."}, ...]` 형식의 **JSON 목록** (txt 아님). input에는 실제 추론과 같은 chat template을 적용한 문자열을 넣는다.

## 4. 보드 추론

- rknn-llm 저장소의 `rkllm_api_demo`(C++)로 먼저 동작과 tok/s를 확인한다 (BOARD-05).
- `llm_svc`는 C API를 ctypes로 감싸거나 데모 프로세스를 감싸는 방식 중 선택한다 (결정 후 decision log).
- 최대 context 길이, 생성 토큰 수, greedy decoding을 고정한다.

## 5. 측정 (experiment-workflow)

- 3단계 비교: ① 기본 모델(서버) ② 학습 모델(서버 fp16) ③ 양자화 모델(보드 .rkllm) — 같은 문항·템플릿·greedy
- 지표: Action Accuracy, Entity Accuracy, JSON Valid Rate, Unsafe Action Rate, tok/s, TTFT, RAM
- 규칙 파서 결과와 같은 표에 놓고 비교

## 출처 (2026-10-02 확인)

- https://github.com/airockchip/rknn-llm (README, benchmark.md, `rkllm-toolkit/packages`, `examples/rkllm_api_demo/export/export_rkllm.py`)
- Rockchip RKLLM SDK 문서 `doc/Rockchip_RKLLM_SDK_EN_1.3.1.pdf` (§2.4 드라이버, §3.2.8 LoRA, Table 3-3 build 인자)
