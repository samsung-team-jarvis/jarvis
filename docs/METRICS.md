# 평가 지표 · 측정 결과

> **규칙:** 실측값만 기록한다. 미측정은 `측정 예정`. 모든 값에 측정일·보드·버전·데이터셋·커밋을 남긴다. 최종 판정은 **보드 기준**.
> 목표치는 달성치가 아니라 개발 우선순위를 정하기 위한 팀 내부 목표다 (5주차 발표 p.14).

## 1. 지표 정의

| 지표 | 정의 | 측정 데이터 | 측정 위치 | 팀 목표 |
|---|---|---|---|---|
| LLM Action Accuracy | Test 발화 중 action이 정답과 일치한 비율 | LLM Test Set | 보드(.rkllm) | ≥ 90% |
| LLM Entity Accuracy | action 일치 건 중 target·파라미터까지 일치한 비율 | LLM Test Set | 보드 | 측정 후 설정 |
| JSON Valid Rate | 출력이 스키마(INTERFACES §3)를 통과한 비율 | LLM Test Set | 보드 | ≥ 98% |
| Unsafe Action Rate | 위험 상황(Hard Negative)에서 실행형 Action을 낸 비율 (Guard 적용 전/후 별도) | Hard Negative Test | 보드 | ≤ 2% |
| STT CER | 글자 오류율, 소음 조건별 | STT Test Set | 보드 | 측정 후 설정 |
| STT→Action Accuracy | 음성 입력부터 최종 action 일치율 | STT Test Set | 보드 | 측정 후 설정 |
| STT RTF | STT 처리시간 / 음성길이 | STT Test Set | 보드 | < 1 |
| YOLO mAP50 | 클래스 평균 | Vision Test Set | 보드(INT8) | ≥ 0.80 |
| YOLO 지연 | 전처리 / NPU / 후처리 ms | Vision Test Set | 보드 | 측정 후 설정 |
| State F1 | 시점별 State 판정 F1 | 통합 시나리오 | 보드 | 측정 후 설정 |
| 위험 미탐율 | 위험 시나리오 중 감지 못한 비율 | 센서·통합 시나리오 | 보드 | 측정 후 설정 |
| 위험 감지→차단 지연 | 위험 조건 충족 → ESP32 출력 OFF (ms) | 센서 시나리오 | 보드+ESP32 | 측정 후 설정 |
| BLE 제어 성공률 | ACK 수신 성공 비율 | 제어 로그 | 보드+ESP32 | ≥ 95% |
| BLE 왕복 지연 | write → ACK (ms) | 제어 로그 | 보드+ESP32 | 측정 후 설정 |
| LLM tok/s | 생성 속도 | 고정 프롬프트 | 보드 | ≥ 10~15 |
| LLM TTFT | 첫 토큰까지 시간 | 고정 프롬프트 | 보드 | 측정 후 설정 |
| E2E 지연 | 발화 끝 → 제어 ACK (구간별 분해) | Skeleton 로그 | 보드 | 측정 후 설정 |
| RAM / SoC 온도 | 동시 구동 시 최대 | 30분 구동 | 보드 | 측정 후 설정 |

> 참고 기준선 (수업 자료, 우리 측정 아님): RK3588 w8a8 TinyLLAMA 1.1B — TTFT 239ms · 24.5 tok/s · 메모리 1,085MB

## 2. 데이터셋 현황

| 구분 | 목표 | 현재 | 최종 갱신 |
|---|---|---|---|
| LLM 명령 | 2,000~3,000쌍 | 측정 예정 | |
| STT 음성 | 500~800 발화 | 측정 예정 | |
| YOLO 이미지 | 800~1,200장 | 측정 예정 | |
| 센서 시나리오 | 20~30개 | 측정 예정 | |
| 통합 시나리오 | 20~30개 | 측정 예정 | |
| 양자화 캘리브레이션 | 300~1,000 발화 (Train에서만) | 측정 예정 | |

## 3. 결과표 (동일 Test Set)

| 지표 | Baseline | v1 | v2 | 최종 | 비고 |
|---|---|---|---|---|---|
| LLM Action Acc (규칙 파서) | 측정 예정 | - | - | | 비교 기준 |
| LLM Action Acc (기본 모델+프롬프트) | 측정 예정 | | | | |
| LLM Action Acc (LoRA, 서버 fp16) | - | 측정 예정 | | | |
| LLM Action Acc (LoRA, 보드 w8a8) | - | 측정 예정 | | | 양자화 전후 비교 |
| JSON Valid Rate | 측정 예정 | | | | |
| Unsafe Action Rate (Guard 전/후) | 측정 예정 | | | | |
| STT CER (quiet/hood/frying/mixed) | 측정 예정 | | | | |
| STT→Action Acc | 측정 예정 | | | | |
| YOLO mAP50 (fp32 / INT8) | 측정 예정 | | | | |
| State F1 | 측정 예정 | | | | |
| BLE 성공률 | 측정 예정 | | | | |
| E2E 지연 | 측정 예정 | | | | |

## 4. 측정 로그

| 날짜 | 지표 | 값 | 보드/버전 | 데이터셋 | 커밋 | 측정자 |
|---|---|---|---|---|---|---|
