# 결정 기록

## 결정 대기 질문

| ID | 질문 | 왜 중요한가 | 답 |
|---|---|---|---|
| Q-01 | 보드 실물: Orange Pi 5인가 5 Plus인가? RAM은 몇 GB? 방열판·팬 있나? | RAM이 8GB 이하면 STT+LLM+YOLO 동시 구동 계획이 바뀜. 문서 표기 통일 필요 | |
| Q-02 | 학사 일정: 중간·최종 발표 시점, 주간보고 요구사항 | Phase 우선순위 조정 | |
| Q-03 | 팀원 중 x86 Linux PC 또는 NVIDIA GPU 보유자? | 없으면 Colab이 학습·RKLLM 변환 기본 경로 | |
| Q-04 | 역할 분담 확정 (워크스트림 ↔ 담당자) | PLAN의 담당 칸 | |
| Q-05 | 마음AI SUDA를 실제로 쓸 수 있나, 범위는? | 의존 여부 결정. 불가 시 "참고"로만 서술 | |
| Q-06 | 모듈 간 통신 방식: MQTT(mosquitto) / ZeroMQ / multiprocessing Queue | INFRA-03 구현 방식 | 추천: MQTT (디버깅·녹화·병렬 개발 용이) |
| Q-07 | LLM 후보 모델 목록 (RKLLM 지원 목록 기준) | LLM-06 비교 범위 | 추천 후보: Llama-3.2-1B, Qwen2.5-0.5B/1.5B-Instruct (지원 여부 확인 필요) |
| Q-08 | 호출어 방식 | 오작동 방지 | 추천 v0: 텍스트 기반 "자비스" 접두 |

## 버전 고정 표 (BOARD-03에서 채움)

| 항목 | 버전 | 확인 방법 | 확인일 |
|---|---|---|---|
| 보드 OS 이미지 | | | |
| 커널 / NPU 드라이버 | | | |
| RKNN-Toolkit2 (변환) | | | |
| rknn-toolkit-lite2 / librknnrt (보드) | | | |
| rkllm-toolkit (변환) | | | |
| librkllmrt (보드) | | | |
| sherpa-onnx | | | |
| ultralytics | | | |
| Python | | | |

> 변환 툴과 보드 런타임은 같은 릴리스로 맞춘다.

## 문서 불일치 정리 (DOC-02)

| 항목 | 수행계획서 | 발표자료 | 통일안 |
|---|---|---|---|
| 보드 | Orange Pi 5 (RK3588S) | Orange Pi 5 Plus (RK3588) | Q-01 답에 따름 |
| 언어 이해 | 오프라인 STT/NLU | VAD→STT→소형 LLM(Function Call) | "NLU = 소형 LLM Function Call 해석기"로 서술 |
| 비전 | 조리 동작/도구 감지 | 객체 Context (pan·burner·hand) | 객체 감지 + 시간 기반 State 추론 |
| STT 지표 | - | WER | CER 주지표 + STT→Action 정확도 (WER 병기 가능) |
| 물리 차단 | 위험 시 물리 차단 | ESP32 직접 제어 | 저전압 모형 차단으로 시연 |

## 확정된 결정 (ADR)

형식: `### ADR-번호 제목` / 날짜 / 결정 / 이유 / 대안

### ADR-001 개발 방식: Walking Skeleton 우선
- 날짜: 2026-10-01
- 결정: 모듈 고도화보다 E2E(말→LED) 연결을 먼저 완성한다 (PLAN Phase 2).
- 이유: 4명 병렬 개발에서 막판 통합 실패가 가장 큰 리스크.

### ADR-002 안전 3계층
- 날짜: 2026-10-01
- 결정: ESP32 자체 안전장치(L0) / 결정론적 Safety Guard(L1) / LLM은 제안만(L2). 위험 감지는 LLM 경로를 거치지 않는다.
- 이유: LLM 환각·Pi 장애가 물리 제어로 이어지지 않게.

### ADR-003 LLM 비교 기준선으로 규칙 파서 사용
- 날짜: 2026-10-01
- 결정: 같은 Test Set에서 규칙 파서와 LLM을 비교하고, LLM 출력 검증 실패 시 규칙 파서로 대체한다.
- 이유: LLM 도입 효과를 수치로 증명 + 안정성 확보.
