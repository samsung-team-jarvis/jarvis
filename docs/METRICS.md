# 평가 지표 · 측정 결과

> **규칙:** 실측값만 기록한다. 미측정은 `측정 예정`. 모든 값에 측정일·보드·버전·데이터셋·커밋을 남긴다. 최종 판정은 **보드 기준**.
> 목표치는 달성치가 아니라 개발 우선순위를 정하기 위한 팀 내부 목표다 (5주차 발표 p.14).
> 2026-10-05 시연 환경을 가상 주방으로 바꿨다 ([decision](./decisions/2026-10-05-virtual-kitchen-demo.md)): 비전·온도·제어 지표는 가상 주방 기준이다. **LLM 결과(§3)는 2026-10-06부터 데이터 v2(장치 8종 · 스키마 v0.2) 기준**이다 (LLM-14). 데이터 v1(장치 3종)으로 잰 2026-10-02 값은 §4 측정 로그에 남아 있고, test가 달라 v2 값과 바로 비교할 수 없다.

## 1. 지표 정의

| 지표 | 정의 | 측정 데이터 | 측정 위치 | 팀 목표 |
|---|---|---|---|---|
| LLM Action Accuracy | Test 발화 중 action이 정답과 일치한 비율 | LLM Test Set | 보드(.rkllm) | ≥ 90% |
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
| LLM Action Acc (LoRA, 서버 fp16) | - | 측정 예정 | | | |
| LLM Action Acc (LoRA, 보드 w8a8) | - | 측정 예정 | | | 양자화 전후 비교 |
| JSON Valid Rate | Qwen3-0.6B 72.6% · Qwen3.5-2B 75.7% | | | | Mac fp16 참고값, 데이터 v2 test (함수 토큰 형식·스키마 통과율) |
| Unsafe Action Rate (Guard 전/후) | Guard 전: 규칙 파서 100% · Qwen3-0.6B 37.5% · Qwen3.5-2B 87.5% / Guard 후: 측정 예정 | | | | n=8 (데이터 v2 Hard Negative test의 REJECT 대상). 전은 설계상 높다 — 모델 값이 낮은 건 안전해서가 아니라 명령을 못 알아들어서. Guard 후는 FUS-03 이후 |
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
