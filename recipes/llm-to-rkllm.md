# Recipe: 소형 LLM 학습 → RKLLM(W8A8) 변환 → 보드 추론·서빙

> 기준 자료: 학교 특강2 (마음AI, [school-materials](../docs/school-materials.md)) + airockchip/rknn-llm. **학교 제공 환경(A100 서버 + 변환 도커 + 보드 배포 이미지)이 기본 경로**이고, Colab 노트북은 서버를 쓸 수 없을 때의 대체 경로다. 실제 실행 결과(BOARD-05·06, LLM-07·08)는 아직 없다.

## 개념 3줄

- **LoRA**: 모델 전체가 아니라 작은 추가 가중치만 학습하는 방법. 변환 전에 베이스에 **병합**해야 한다.
- **양자화(W8A8)**: 가중치·활성값을 8비트로. RK3588 NPU가 가속하는 형식이다. 손실 압축이라 변환 성공 ≠ 품질 유지 → 반드시 원본 vs 양자화 비교.
- **chat template / eos**: 모델이 대화를 인식하는 형식과 "여기서 끝" 신호. 학습·평가·캘리브레이션·보드 추론에서 **완전히 같아야** 한다.

## 환경 (특강 p.8, 19)

| 단계 | 어디서 | 비고 |
|---|---|---|
| 학습·평가 | 클라우드 GPU 서버 (x86_64, A100 80GB) | 1B~3B는 A100 한 장으로 충분 |
| RKLLM 변환·보드용 데모 빌드 | 같은 서버의 **제공 도커** (`run.sh`) | 변환 툴킷은 x86_64 전용. 보드 없이 변환 가능 |
| 추론·서빙 | Orange Pi 5 Plus (배포 이미지, RKNPU v0.9.8) | `librkllmrt.so` 1.3.0 |
| (대체) 변환 | Colab — [`convert_rkllm.ipynb`](../training/colab/convert_rkllm.ipynb) | 서버를 쓸 수 없을 때. 버전을 도커와 같은 1.3.0으로 맞출 것 |

## 0. 모델 선택

- 후보와 기준: [결정 사항](../docs/decisions/open-questions.md) Q-07. 특강 예시 모델은 Llama-3.2-1B-Instruct, 비교용 Qwen3.5-2B.
- 지원 계열(RKLLM 1.3.0): Llama/TinyLlama, Qwen2·2.5·3·3.5, Phi2·3, Gemma2·3·3n·4, DeepSeek-R1-Distill, MiniCPM 등. 목록에 없는 구조는 변환이 막힐 수 있다.
- Base가 아니라 **Instruct(대화용) 모델**을 쓴다.

## 1. 데이터 (LLM-01~05)

- 출력 형식: [Q-10](../docs/decisions/open-questions.md) (함수 토큰 형식) · 스키마: [interfaces](../docs/architecture/interfaces.md) §3
- 학습 데이터는 학습 도구가 요구하는 `messages`(system / user / assistant) 형식으로 저장. **system 지시는 평가·캘리브레이션·보드에서도 같은 문장**.
- 토큰화 후 길이 분포를 보고 `max_context`를 정한다 (명령문은 짧으므로 1024로 충분할 가능성이 높음 — 측정으로 결정).
- 분할은 그룹 단위 (템플릿·세션), 같은 대화나 유사 변형이 train과 test에 섞이지 않게.

## 2. 학습 (LLM-07)

- 전체 / LoRA / QLoRA 중 선택. **LoRA·QLoRA는 반드시 병합해서 fp16/fp32 HF 모델 디렉터리로 저장** (QLoRA는 4bit 베이스를 fp16으로 복원 → 병합 → 저장). 툴킷 API에는 LoRA 분리 변환 인자(`model_lora`)가 있지만, 학교 도커 절차는 병합 모델을 입력으로 한다.
- 시작값은 선정 모델의 권장 예제 설정. learning rate·epoch·scheduler·warmup·seed를 기록.
- 소량 시험 학습(로딩 → 학습 → 저장 → 재로딩)을 먼저 끝까지 돌린다.
- 최저 loss만으로 고르지 말고 검증 문항의 실제 답을 본다.

## 3. 변환 준비물 (특강 p.23~26)

도커 마운트 3개:

| 폴더 | 컨테이너 경로 | 내용 |
|---|---|---|
| `model/` | `/work/model` (읽기 전용) | 병합된 HF 모델 |
| `data/` | `/work/data` | `config.yaml`, `queries.json`, `data_quant.json` |
| `output/` | `/work/output` | `*.rkllm`, `*.log`, `demo_Linux_aarch64/` |

`config.yaml` (팀이 고치는 유일한 파일):

| 키 | 값 |
|---|---|
| `team` / `domain` | 팀·도메인 이름 (파일 이름에 들어감) |
| `prompt_template` / `system_prompt` | 학습 때와 같은 chat template·system 지시 |
| `quantized_dtype` | `w8a8` (정확도가 아쉬우면 `w8a8_g128`) |
| `optimization_level` | 1 = 정확도 우선, 0 = 속도 우선 (실험 대상) |
| `max_context` | 32의 배수, ≤ 16384 |
| `calib_stop_at` | 종료 토큰 (예: `<\|eot_id\|>` 또는 우리 함수 토큰의 끝 토큰) |
| `target_platform` / `num_npu_core` | `RK3588` / `3` — 전 팀 고정 |

`queries.json`: 실제 발화 **300~1,000건** (유형·말투 고르게, Train에서만). `./run.sh calib`가 원본 모델로 target을 생성해 `data_quant.json`을 만든다. 생성 후 앞 10건 + 무작위 10건을 눈으로 검수한다 — target이 정답 뒤에 설명문을 길게 달고 있으면 종료 토큰 설정 문제다 (`eos_token_id`가 `config.json`·`generation_config.json`에도 있어야 함).

## 4. 변환 (`run.sh`)

```bash
./run.sh check        # 아키텍처 지원·chat template·dtype·max_context 점검 → CHECK PASSED 가 나와야 다음
./run.sh calib        # queries.json → data_quant.json
./run.sh convert      # 양자화 → output/<팀>-<도메인>_w8a8_opt1_cal<N>.rkllm + .log
./run.sh build-demo   # 보드용 llm_demo · lib/librkllmrt.so 크로스 컴파일
```

- 산출물 크기가 원본 HF 모델의 1/3~1/4이면 정상. 실패하면 로그 마지막부터 dtype·max_context·모델 경로 순으로 확인.
- 파일 이름에 설정이 들어 있으니 이름을 바꾸지 않는다. `config.yaml`·`data_quant.json`은 재현용으로 보관 (Drive).

## 5. 보드 추론 (특강 p.27~29)

```bash
# 보드: ~/rkllm/<이름>.rkllm, ~/rkllm/demo_Linux_aarch64/ (llm_demo와 lib/ 같은 폴더)
md5sum ~/rkllm/*.rkllm                 # 서버와 같은지 (끊긴 파일은 init 실패로 나타남)
cd ~/rkllm/demo_Linux_aarch64
export LD_LIBRARY_PATH=./lib
sudo bash fix_freq_rk3588.sh           # 클럭 고정 — 측정 전 필수
export RKLLM_LOG_LEVEL=1               # TTFT · tok/s · 메모리 로그
./llm_demo ../<이름>.rkllm 256 4096    # max_new_tokens, max_context_len(변환 시 max_context 이하)
```

## 6. 서빙 → `llm_svc` (특강 p.30~31, 37)

- **제공 FastAPI 서버**(보드에서 ctypes로 librkllmrt 로드, OpenAI 호환 `POST /v1/chat/completions`, 스트리밍)를 그대로 쓴다.
- 우리 `llm_svc`는 버스의 `stt/text`를 받아 이 서버에 HTTP로 요청하고, 출력(함수 토큰)을 파싱해 `llm/function_call`로 발행하는 **어댑터**다. 검증 실패 시 규칙 파서로 대체 ([decision](../docs/decisions/2026-10-01-rule-parser-baseline.md)).
- 명령 해석용 권장값: `top_k=1`(결정적), `max_new_tokens` 64 안팎(짧은 명령형), `keep_history=0`(문맥은 구조화 context로 직접 넣는다, LLM-12).

## 7. 측정 (experiment-workflow, 특강 p.32)

- 같은 문항·템플릿·greedy로 ① 기본 모델(서버) ② 학습 모델(서버) ③ 양자화 모델(보드) 비교
- 지표: Action Accuracy, Entity Accuracy, 형식 Valid Rate, Unsafe Action Rate, TTFT, tok/s, 메모리, NPU Load
- 1B 기준 약 20 tok/s · 1.1GB 근처면 정상(특강). 절반 이하면 클럭 고정·드라이버·코어 수 확인
- 규칙 파서 결과와 같은 표에 놓고 비교

## 출처

- 학교 특강2 p.4~32 (원본은 팀 Drive)
- https://github.com/airockchip/rknn-llm (README, `examples/rkllm_api_demo/export/export_rkllm.py`)
