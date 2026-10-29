# 평가 지표 · 측정 결과

> **규칙:** 실측값만 기록한다. 미측정은 `측정 예정`. 모든 값에 측정일·보드·버전·데이터셋·커밋을 남긴다. 최종 판정은 **보드 기준**.
> 목표치는 달성치가 아니라 개발 우선순위를 정하기 위한 팀 내부 목표다 (5주차 발표 p.14).
> 2026-10-05 시연 환경을 가상 주방으로 바꿨다 ([decision](./decisions/2026-10-05-virtual-kitchen-demo.md)): 비전·온도·제어 지표는 가상 주방 기준이다. **LLM 결과(§3)는 2026-10-06부터 데이터 v2(장치 8종 · 스키마 v0.2) 기준**이다 (LLM-14). 데이터 v1(장치 3종)으로 잰 2026-10-02 값은 §4 측정 로그에 남아 있고, test가 달라 v2 값과 바로 비교할 수 없다.

## 1. 지표 정의

| 지표 | 정의 | 측정 데이터 | 측정 위치 | 팀 목표 |
|---|---|---|---|---|
| LLM Action Accuracy | Test 발화 중 action이 정답과 일치한 비율 | LLM Test Set | 보드(GGUF, llama.cpp CPU — 2026-10-29부터) | ≥ 90% |
| LLM Entity Accuracy | action 일치 건 중 target·파라미터까지 일치한 비율 | LLM Test Set | 보드 | 측정 후 설정 |
| JSON Valid Rate | 출력이 스키마(interfaces §3)를 통과한 비율 | LLM Test Set | 보드 | ≥ 98% |
| Unsafe Action Rate | 위험 상황(Hard Negative, `expect_guard: REJECT`)에서 실행형 Action이 실행 단계까지 간 비율 (Guard 적용 전/후 별도). LLM은 말 그대로 해석하므로 **Guard 전은 설계상 높다** ([decision](./decisions/2026-10-02-llm-literal-guard-decides.md)) | Hard Negative Test | 보드 | Guard 후 ≤ 2% |
| STT CER | 글자 오류율, 소음 조건별 | STT Test Set | 보드 | 측정 후 설정 |
| STT→Action Accuracy | 음성 입력부터 최종 action 일치율 | STT Test Set | 보드 | 측정 후 설정 |
| STT RTF | STT 처리시간 / 음성길이 | STT Test Set | 보드 | < 1 |
| YOLO mAP50 | 클래스 평균 | Vision Test Set (가상 주방 캡처 화면) | 보드(INT8) | ≥ 0.80 |
| YOLO 지연 | 전처리 / NPU / 후처리 ms | Vision Test Set | 보드 | 측정 후 설정 |
| State F1 | 시점별 State 판정 F1 | 통합 시나리오 | 보드 | 측정 후 설정 |
| 위험 미탐율 | 위험 시나리오 중 감지 못한 비율 | 온도·통합 시나리오 | 보드 | 측정 후 설정 |
| 위험 감지→차단 지연 | 위험 조건 충족 → 가상 주방의 가열 장치 OFF (ms) | 온도 시나리오 | 보드+가상 주방 | 측정 후 설정 |
| 제어 성공률 | 제어 명령 중 결과 확인을 받은 비율 | 제어 로그 | 보드+가상 주방 | ≥ 95% |
| 제어 왕복 지연 | 제어 명령 → 결과 확인 (ms) | 제어 로그 | 보드+가상 주방 | 측정 후 설정 |
| LLM tok/s | 생성 속도 | 고정 프롬프트 | 보드 | ≥ 10~15 |
| LLM TTFT | 첫 토큰까지 시간 | 고정 프롬프트 | 보드 | 측정 후 설정 |
| E2E 지연 | 발화 끝 → 제어 결과 확인 (구간별 분해) | Skeleton 로그 | 보드 | 측정 후 설정 |
| RAM / SoC 온도 | 동시 구동 시 최대 | 30분 구동 | 보드 | 측정 후 설정 |

> 참고 기준선 (학교 특강2 p.32의 RK3588 공식 벤치마크, w8a8·64 tokens — **우리 측정 아님**): Qwen3 0.6B 214ms · 32.2 tok/s · 774MB / TinyLLAMA 1.1B 239ms · 24.5 tok/s · 1,085MB / Qwen2.5 1.5B 412ms · 16.3 tok/s · 1,659MB

## 2. 데이터셋 현황

| 구분 | 목표 | 현재 | 최종 갱신 |
|---|---|---|---|
| LLM 명령 | 2,000~3,000쌍 | 데이터 v2: 3,015쌍 + Hard Negative 165 (train 2,198 · val 508 · test 474, 사람 검수 전) — 장치 8종 · 함수 14개. v1(2,234쌍 + 84, 장치 3종)은 고정본 | 2026-10-06 (#86) |
| STT 음성 | 500~800 발화 | 40 (spk01 val, quiet, MacBook 마이크) | 2026-10-02 (#61) |
| YOLO 이미지 (가상 주방 캡처) | 800~1,200장 | 측정 예정 | |
| 온도 시나리오 (가상 주방) | 20~30개 | 측정 예정 | |
| 통합 시나리오 | 20~30개 | 측정 예정 | |
| 양자화 캘리브레이션 | 300~1,000 발화 (Train에서만) | 502 (데이터 v2 train에서) | 2026-10-06 (#86) |

## 3. 결과표 (동일 Test Set)

| 지표 | Baseline | v1 | v2 | 최종 | 비고 |
|---|---|---|---|---|---|
| LLM Action Acc (규칙 파서) | **82.5%** (Entity 82.1%) | - | - | | 비교 기준. 데이터 v2 test n=474. 규칙이라 보드에서도 같은 값 (데이터 v1 test n=354에서는 79.9%) |
| LLM Action Acc (기본 모델+프롬프트) | Qwen3-0.6B 25.7% · Qwen3.5-2B 44.5% (Entity 17.5% · 35.4%) | | | | **Mac fp16 참고값**, 데이터 v2 test · 지시문 v0.2 — 보드(.rkllm) 측정은 BOARD-05 이후. Llama-3.2-1B는 HF 승인 대기. 데이터 v1·지시문 v0.1에서는 32.8% · 66.1% |
| LLM Action Acc (LoRA, 서버 fp16) | - | Qwen3-0.6B LoRA v1: **72.6%** (Entity 71.1%) | LoRA v2 (보강 208문장): **78.5%** (Entity 77.6%) · LoRA v3b (+ 새 말투 875문장, LLM-15): 83.5% (Entity 80.6%) · LoRA v4 (+ 새 말투 v2 526문장, LLM-16): **86.9%** (Entity **86.5%**) · v5 (+ 162문장, LLM-17): 87.3% (Entity 86.3%, v4와 차이 없음) · **v4 + 규칙 파서 대체 (LLM-09): 89.2% (Entity 88.8%)** | | **Mac MPS fp16 참고값** (서버 아님), 데이터 v2 test, 학습 모델용 짧은 지시문·예시 없음. v4가 Action·Entity 모두 규칙 파서(82.5% / 82.1%)를 넘었다 (틀린 실행 12 → 11). 같은 수를 같은 말투로 더한 v3a는 79.3% (Entity 75.3%, 틀린 실행 11 → 33). val은 v1 83.9% → v2 94.9% → v3b 95.9% → v4 98.8%이지만 보강 방향을 val 오류로 정해 낙관적이다 |
| LLM Action Acc (LoRA v4, GGUF · llama.cpp CPU) | - | **q8_0 87.1%** (Entity 86.7%, 형식 97.3%) · f16 87.1% (86.7%) · **q8_0 + 규칙 파서 대체 89.7% (Entity 89.2%)** | | | **Mac CPU 4스레드 참고값** (LLM-18), 데이터 v2 test. 같은 모델의 HF fp16(MPS) 86.9% / 86.5% / 97.5%와 같은 수준 — 8비트 양자화 손실이 보이지 않는다. 보드 CPU 값은 측정 예정. RKLLM(보드 w8a8)은 쓰지 않는다 ([decision](./decisions/2026-10-29-llamacpp-and-rebalance.md)) |
| JSON Valid Rate | Qwen3-0.6B 72.6% · Qwen3.5-2B 75.7% | Qwen3-0.6B LoRA v1 96.0% | LoRA v2 96.6% · v3b 99.8% · v4 97.5% | | Mac fp16 참고값, 데이터 v2 test (함수 토큰 형식·스키마 통과율) |
| Unsafe Action Rate (Guard 전/후) | Guard 전: 규칙 파서 100% · Qwen3-0.6B 37.5% · Qwen3.5-2B 87.5% / Guard 후: 측정 예정 | Guard 전: Qwen3-0.6B LoRA v1 100% (8/8) | Guard 전: LoRA v2 100% (8/8) | | n=8 (데이터 v2 Hard Negative test의 REJECT 대상). 전은 설계상 높다 — 모델 값이 낮은 건 안전해서가 아니라 명령을 못 알아들어서. Guard 후는 FUS-03 이후 |
| STT CER (quiet/hood/frying/mixed) | 측정 예정 | | | | |
| STT→Action Acc | 측정 예정 | | | | |
| YOLO mAP50 (fp32 / INT8) | 측정 예정 | | | | |
| State F1 | 측정 예정 | | | | |
| 제어 성공률 (가상 주방) | 측정 예정 | | | | |
| E2E 지연 | 측정 예정 | | | | |

## 4. 측정 로그

| 날짜 | 지표 | 값 | 보드/버전 | 데이터셋 | 커밋 | 측정자 |
|---|---|---|---|---|---|---|
| 2026-10-02 | E2E 지연 — 발화 끝 → `llm/function_call` (Guard·BLE 미구현 구간 제외) · **Mac 참고값** | 평균 609 ms · p50 592 · p95 705 · 최대 705 (vad_wait 평균 540 / stt 68 / to_call 1) | M1 Pro Mac / sherpa-onnx 1.13.8, SenseVoice int8 CPU 4스레드, 규칙 파서, MQTT(Docker mosquitto 2) | macOS `say` 합성 명령 wav `--realtime` (n=14: 명령 4종×3회 + 2) — 사람 음성·보드 아님 | 37e43d1 + `bench/latency.py`(#45) | 이현종 |
| 2026-10-02 | 규칙 파서 Baseline (FUS-06) — Action Acc / Entity Acc / Valid / Unsafe(Guard 전) | 79.9% / 79.7% / 100% / 100% (8/8) | 플랫폼 무관 (Mac에서 실행) / `services/llm_svc/rule_parser.py` | LLM split v1 test (n=354: 일반 337 + Hard Negative 17) | 5c5cc24 | 이현종 |
| 2026-10-02 | 기본 모델+프롬프트 Baseline (LLM-06) Qwen3-0.6B — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | 32.8% / 19.2% / 69.2% / 37.5% (3/8), 평균 726 ms/건 | M1 Pro Mac MPS fp16 / torch 2.14.1, transformers 5.18.0, 시스템 프롬프트 + few-shot 13(train), greedy | LLM split v1 test (n=354) | 5c5cc24 | 이현종 |
| 2026-10-02 | 기본 모델+프롬프트 Baseline (LLM-06) Qwen3.5-2B — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | 66.1% / 60.2% / 88.7% / 50.0% (4/8), 평균 2,914 ms/건 (Mac은 최적화 커널 없는 기본 구현이라 느림) | 위와 같음 | LLM split v1 test (n=354) | 5c5cc24 | 이현종 |
| 2026-10-06 | 규칙 파서 Baseline (FUS-06) — Action Acc / Entity Acc / Valid / Unsafe(Guard 전) | 82.5% / 82.1% / 100% / 100% (8/8). val: 80.1% / 78.7% (n=508) | 플랫폼 무관 (Mac에서 실행) / `services/llm_svc/rule_parser.py` (스키마 v0.2, 고치지 않음) | LLM split **v2** test (n=474: 일반 445 + Hard Negative 29) | 318de25 | 이현종 |
| 2026-10-06 | 기본 모델+프롬프트 Baseline (LLM-06) Qwen3-0.6B — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | 25.7% / 17.5% / 72.6% / 37.5% (3/8), 평균 886 ms/건 | M1 Pro Mac MPS fp16 / torch 2.14.1, transformers 5.18.0, 지시문 v0.2(장치 8종·함수 14개) + few-shot 17(train), greedy | LLM split v2 test (n=474) | 318de25 | 이현종 |
| 2026-10-06 | 기본 모델+프롬프트 Baseline (LLM-06) Qwen3.5-2B — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | 44.5% / 35.4% / 75.7% / 87.5% (7/8), 평균 3,661 ms/건 | 위와 같음 | LLM split v2 test (n=474) | 318de25 | 이현종 |
| 2026-10-06 | LoRA v1 (LLM-07) Qwen3-0.6B — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 72.6% / 71.1% / 96.0% / 100% (8/8), 평균 335 ms/건. val 83.9% / 83.1% / 97.6% (n=508) | M1 Pro Mac MPS — 학습 fp32·저장 fp16 / torch 2.14.1, transformers 5.18.0, peft 0.21.2. LoRA r16·α32·dropout 0.05(선형층 7종), lr 2e-4 cosine·warmup 20, 배치 16, 3 epoch(414 step, 31분), seed 0. val loss 0.071 → 0.060 → 0.068. 평가: 학습 모델용 짧은 지시문·예시 없음, greedy | LLM split v2 train 2,198으로 학습, test (n=474) | 1079e3c (학습 시작 때는 미커밋 — MPS 경로 코드 동일) | 이현종 |
| 2026-10-06 | LoRA v2 (LLM-11) Qwen3-0.6B, 오류 유형 보강 — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 78.5% / 77.6% / 96.6% / 100% (8/8), 평균 331 ms/건 (v1 72.6% / 71.1% / 96.0%). test 오류 137 → 106건, 틀린 실행 20 → 11건. val 94.9% / 94.3% / 99.4% (보강 방향을 val로 정해 낙관적) | LoRA v1과 같은 설정·환경 (3 epoch 453 step, 34분). val loss 0.038 → 0.024 → 0.021. 바꾼 것은 학습 데이터 하나: train 2,198 + 보강 208 (`augment_v1.jsonl`) | LLM split v2 test (n=474) — v1과 같은 test | 8d926e1 | 이현종 |
| 2026-10-13 | LoRA v3a (LLM-15 실험 A) Qwen3-0.6B, 같은 말투 더 — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 79.3% / 75.3% / 97.0% / 100% (8/8), 평균 338 ms/건. test 오류 106 → 117건, 틀린 실행 11 → 33건. val 94.5% / 92.7% / 99.2% | LoRA v2와 같은 설정·환경 (3 epoch 618 step, 44분). val loss 0.036 → 0.028 → 0.029. 바꾼 것은 학습 데이터 하나: v2 학습 데이터 + 기존 train 템플릿의 안 쓴 장치·값 조합 875 (`more_v1.jsonl`) | LLM split v2 test (n=474) — v1·v2와 같은 test | f5eace7 | 이현종 |
| 2026-10-13 | LoRA v3b (LLM-15 실험 B) Qwen3-0.6B, 새 말투 — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 83.5% / 80.6% / 99.8% / 100% (8/8), 평균 327 ms/건. test 오류 106 → 92건, 틀린 실행 11 → 12건. val 95.9% / 95.7% / 99.6% | v3a와 같음 (3 epoch 618 step, 44분). val loss 0.031 → 0.012 → 0.013. 더한 것: 새 말투 템플릿 131개의 875문장 (`variety_v1.jsonl`) — A와 같은 수 | LLM split v2 test (n=474) — 같은 test | f5eace7 | 이현종 |
| 2026-10-13 | LoRA v4 (LLM-16) Qwen3-0.6B, 새 말투 v2 더 — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 86.9% / 86.5% / 97.5% / 100% (8/8), 평균 335 ms/건. test 오류 92 → 64건, 틀린 실행 12 → 11건, 규칙 위반 1 → 12건. val 98.8% / 98.8% / 100% | v3b와 같은 설정 (3 epoch 714 step, 49분). val loss 0.013 → 0.005 → 0.004. 더한 것: v3b val 오류·페르소나 말버릇으로 만든 새 말투 템플릿 63개의 526문장 (`variety_v2.jsonl`) | LLM split v2 test (n=474) — 같은 test | c5cab1a | 이현종 |
| 2026-10-13 | LoRA v5 (LLM-17) Qwen3-0.6B, 새 말투 v3 더 — Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 87.3% / 86.3% / 98.3% / 100% (8/8), 평균 335 ms/건. test 오류 64 → 65건, 틀린 실행 11 → 10건, 긴급 정지 오판 7 → 8건. val 98.8% / 98.8% / 99.8% (오류 6 → 6) | v4와 같은 설정 (3 epoch 747 step, 52분). val loss 0.022 → 0.005 → 0.003. 더한 것: v4 val 오류로 만든 새 말투 템플릿 18개의 162문장 (`variety_v3.jsonl`). **v4와 차이 없음** — 대표 모델은 v4로 둔다 | LLM split v2 test (n=474) — 같은 test, 이 test로 고르는 마지막 비교 | fb32b33 | 이현종 |
| 2026-10-13 | LoRA v4 + 규칙 파서 대체 (LLM-09) — LLM 출력이 검증(`parse_tokens`)에 실패하면 규칙 파서 결과를 씀 · Action / Entity · **Mac 참고값** | test 89.2% / 88.8% (v4만 86.9% / 86.5%). 대체 12건(LLM Valid 97.5%) 중 11건 맞음. 틀린 수 64 → 53, 규칙 위반 12 → 0, 틀린 실행 11 → 11. val 98.8% / 98.8% (대체 0건) | v4가 이미 낸 출력(`bench/llm_eval.py --csv`)에 `llm_svc`와 같은 함수(`interpret.resolve`)를 적용 (`bench/llm_fallback.py`, 모델 재실행 없음). 대체 정책은 2026-10-01 결정대로 — test를 보고 고르지 않음 | LLM split v2 test (n=474) — 같은 test | c276fba | 이현종 |
| 2026-10-29 | LoRA v4 GGUF q8_0 (LLM-18) — llama.cpp CPU · Action / Entity / Valid / Unsafe(Guard 전) · **Mac 참고값** | test 87.1% / 86.7% / 97.3% / 100% (8/8), 평균 287 ms/건 (다른 작업 없이 다시 잼). + 규칙 파서 대체: 89.7% / 89.2% (대체 13건 중 12건 맞음, 틀린 실행 11). val 98.6% / 98.6% / 100%. 파일 639 MB | M1 Pro Mac CPU 4스레드 (Metal 끔) / llama-cpp-python 0.3.36 (llama.cpp 0c1e570), 학습과 같은 입력 문자열(`prompt.chat_prompt`, tokenizer 결과와 글자까지 같음), greedy, 최대 48토큰. 변환: `training/convert/hf_to_gguf.sh` (같은 커밋의 convert_hf_to_gguf.py) | LLM split v2 test (n=474) · val (n=508) — 같은 test, 고르기 아님(양자화 손실 확인) | 513ac59 | 이현종 |
| 2026-10-29 | LoRA v4 GGUF f16 (LLM-18) — 같은 조건 · **Mac 참고값** | test 87.1% / 86.7% / 97.3% / 100% (8/8), 평균 351 ms/건. + 규칙 파서 대체 89.7% / 89.2%. val 98.8% / 98.8% / 100%. 파일 1.2 GB. test 출력이 q8_0과 다른 문장 3건, 정답 수는 같음 | 위와 같음 | 위와 같음 | 513ac59 | 이현종 |
| 2026-10-29 | E2E 지연 — 발화 끝 → 가상 주방 확인(`control/result`), **노트북 시연 구성 · Mac 참고값** (INFRA-15) | e2e 2,490 / 1,171 ms (화구·후드 명령 2건), 긴급 정지 1건은 빠른 경로로 제어 (LLM 결과는 중복으로 무시). 구간 평균: vad_wait 580 · stt 54 · to_call(LLM) 1,112 (552~1,824, 첫 문장이 가장 느림) · to_guard 2 · to_ack 3 ms. 명령 3건 모두 가상 주방 실행 확인, 그중 1건은 LLM 검증 실패 → 규칙 파서 | M1 Pro Mac / 서비스 7개 동시(`scripts/launch_demo.yaml`): SenseVoice int8 CPU, LLM v4 GGUF q8_0 llama.cpp CPU 4스레드, Safety Guard(상태 COOKING 가정), 가짜 가상 주방, TTS, MQTT(Docker mosquitto 2) | macOS 합성 음성 `data/stt/mac_tts/four_commands.wav` `--realtime` — 4문장 중 3문장만 받아쓰기됨(“타이머 3분” 누락), 사람 음성·보드 아님 | 4781454 + `bench/latency.py` | 이현종 |
| 2026-10-29 | YOLO 지연 — 전처리 / 추론 / 후처리, COCO 사전학습 YOLOv8n (VIS-05·08) · **Mac 참고값** | 2~4 / 75~91 / 3~5 ms (17장). mAP는 측정 예정 (가상 주방 데이터 없음) | M1 Pro Mac / onnxruntime 1.31.1 CPU 2스레드, rknn_model_zoo YOLOv8n ONNX, 입력 640×640 letterbox, `vision_svc` | rknn_model_zoo 예제 사진(bus.jpg) + 빈 화면, MQTT `kitchen/frame` 1초에 4장 — 가상 주방 화면 아님 | a744158 | 이현종 |
| 2026-10-29 | LoRA v4 GGUF q8_0 — 입력 처리 스레드를 4로 맞춘 뒤 (LLM-12 중 발견) · **Mac 참고값** | test 87.1% / 86.7% / 97.3% (출력 474건 모두 이전과 같음), 평균 **204 ms/건** (이전 287). 같은 6문장×2 반복: 기본값(코어 10개) 평균 691~745 · 최대 2,485 ms → 4스레드 216~225 · 최대 296 ms | M1 Pro Mac CPU, llama-cpp-python 0.3.36, `n_threads=n_threads_batch=4` | LLM split v2 test (n=474) | 32234d9 | 이현종 |
| 2026-10-29 | E2E 지연 — 노트북 시연 구성, 대명사 "그거" 포함 (LLM-12) · **Mac 참고값** | 발화 끝 → 가상 주방 확인 1,091 · 827 / 1,064 · 825 / 1,113 · 866 ms (3회, 각 "후드 켜 줘" · "그거 세게 해 줘"), LLM 구간 첫 문장 444~475 · 둘째 210~257 ms. "그거 꺼 줘"는 받아쓰기가 흔들림("그것꺼 죠" → 후드 끔 / "그것거 죠" → 지원 외) | 위 구성 + `launch_demo.yaml` (vision_svc 없음), MQTT(Docker mosquitto 2) | macOS 합성 음성(Yuna) 3문장, 문장 간격 3 s에서는 음성 응답 재생 중 입력 무시(에코 방지)로 셋째 문장이 잘림 → 6 s로 다시 | 32234d9 + `bench/latency.py` | 이현종 |
| 2026-10-29 | 자원 — 서비스별 CPU % (코어 하나 = 100%, 평균/최대)·메모리 RSS 최대, 노트북 시연 구성 전체 (BOARD-08) · **Mac 참고값** | 합계 **CPU 77.7 / 219.5 %, 메모리 2,210 MB** (57초). llm_svc 6.2 / 100.1 % · 1,336 MB (GGUF 639 MB mmap 포함) · audio_svc 8.3 / 60.4 % · 675 MB (STT·VAD·TTS) · vision_svc 67.1 / 82.4 % · 143 MB (1초에 약 3.6장 처리) · recorder·fake_kitchen·safety_guard·kitchen_gw 각 0.1~0.4 % · 19~24 MB. 같은 실행에서 명령 3건 처리(발화 끝 → 가상 주방 확인 1,222 · 861 ms), 화면 271장 보내 244장 인식 | M1 Pro Mac (논리 코어 10개) / `launch_demo.yaml` 7개 서비스, LLM v4 GGUF q8_0 CPU 4스레드, YOLOv8n onnxruntime CPU 2스레드, MQTT(Docker mosquitto 2 — 측정 밖) | 가짜 가상 주방이 이미지 2장(사람 있음·없음)을 1초에 4장, macOS 합성 음성 명령 3개 (`--realtime`) | 95f95a2 + `bench/resources.py` | 이현종 |
| 2026-10-29 | 음성 → 명령, **서비스와 같은 구간 자르기(VAD) 경로** — 호출어 인식 / CER / Action / 전체 일치 (STT-11, #128) · **Mac 참고값** | 앞여유 없음(이전 서비스): 19/34 · 18.5% · 18/34 · 16/34 → **앞여유 0.3 s: 31/34 · 7.9% · 28/34 · 25/34**. 이전 STT 기록(호출어 97.1%, CER 10.6%)은 파일을 통째로 받아쓴 값이라 첫 음절 잘림이 드러나지 않았다 | M1 Pro Mac / Silero VAD(threshold 0.5, min_silence 0.5 s) → SenseVoice int8 → 호출어 → 오인식 사전 → LLM v4 GGUF q8_0 + 규칙 파서 대체, 상태 COOKING | spk01 val 40문장 (명령 34 + 호출어 없음 6), MacBook 마이크 quiet — **val 화자 1명, 조정 근거** | 2794d89 | 이현종 |
| 2026-10-29 | 시연 리허설 — 대본 7단계 중 Guard 판정이 기대와 맞은 단계 (DOC-09, #128) · **Mac 참고값** | 4/7 (후드 켜기 · 1번 화구 세게 · 지원 외 · 긴급 정지). 실패: "그거 약하게"(받아쓰기 "약하 게" → LLM 지원 외), "결제해 줘"("결 해 줘" → 네로 해석), "네, 맞아요"(앞 단계 실패로 질문 없음). 명령 발화 끝 → 가상 주방 확인 887 · 1,133 ms | `launch_demo.yaml` 노트북 시연 구성, MQTT(Docker mosquitto 2) | macOS 합성 음성(Yuna) `bench/rehearsal/demo.yaml`, 문장 사이 8 s — 사람 음성 아님 | 2794d89 + `bench/rehearsal.py` | 이현종 |
| 2026-10-29 | 음성 → 명령, 서비스 경로 — 숫자 정규화 전/후 Action · 전체 일치 (STT-10, #130) · **Mac 참고값** | GGUF LLM + 규칙 파서 대체: 28 · 25 → **29 · 28** / 34. 규칙 파서만: 26 · 25 → 28 · 27 / 34. 글로 된 val 문장 중 규칙에 걸리는 39개(전체 508)는 전후 모두 39/39 전체 일치. test에서 걸리는 문장은 36개(건수만) | VAD 앞여유 0.3 s 받아쓰기(#128)는 같고, `command_text`에 `numerals` 추가. LLM v4 GGUF q8_0, 상태 COOKING | spk01 val 40문장(명령 34) — val 화자 1명, 조정 근거 | 437b861 | 이현종 |
| 2026-10-29 | 장시간 구동 30분 — 서비스 유지·제어 실패·생존 신호 최대 간격·LLM 시간 추세·메모리 추세 (BOARD-09) · **Mac 참고값** | 32분 동안 서비스 7개 모두 유지(종료 0). 받아쓰기 175 · 명령 150 · 가상 주방 제어 74건(**실패 0**) · 사람 감지 6,929장. 생존 신호 최대 간격 1.1~1.7 s. LLM 1건 앞 절반 평균 329 → 뒤 절반 229 ms(최대 806, 느려지지 않음). RSS 처음 5분 → 마지막 5분: llm_svc 720 → 522 · vision_svc 106 → 99 · **audio_svc 342 → 398 MB(+56)** · 나머지 ±3 MB. CPU 합계 평균 88% · 최대 344%(코어 하나 = 100%) | M1 Pro Mac / `launch_demo.yaml` 7개 서비스 + 가짜 가상 주방 화면 1초에 4장, LLM v4 GGUF q8_0 CPU 4스레드, MQTT(Docker mosquitto 2) | 리허설 대본(`bench/rehearsal/demo.yaml`) 합성 음성 25회 이어 붙임(29.8분, `--realtime`) — 단계별 결과는 리허설 1회와 같은 양상(결제 요청은 받아쓰기 "결 해 줘"로 매번 실패) | 7161181 + `bench/resources.py` | 이현종 |
