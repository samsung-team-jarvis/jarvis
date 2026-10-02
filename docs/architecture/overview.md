# 시스템 아키텍처 (v0.1 초안)

## 1. 전체 흐름

```
[핀마이크(USB)] → audio_svc : Silero VAD → STT(SenseVoice, CPU) ──┐ stt/text
[USB 웹캠]      → vision_svc: YOLOv8n .rknn (NPU core0, 3~5fps) ───┤ vision/objects
[ESP32 센서] ─BLE notify→ ble_gw : 온도·전류 (1Hz) ───────────────┤ sensor/reading
                                                                   ▼
             ┌──────────── fusion_svc (State Machine + 현재 Context) ────────────┐
             │     stt/text + context ↓              ↑ llm/function_call         │
             │              llm_svc : RKLLM .rkllm (NPU core1~2)                 │
             │              (검증 실패 시 규칙 파서로 대체)                       │
             └─────────────────────────────┬─────────────────────────────────────┘
                                           ▼
                 safety_guard : 화이트리스트 · 스키마 검증 · 위험 규칙 (결정론적)
                                           ▼ control/command (허용된 것만)
                 ble_gw → ESP32 → 릴레이/LED/USB팬/부저   ← ACK(seq) → control/result
                 ESP32 자체 안전장치: 온도 상한 초과 또는 하트비트 끊김 → 모든 출력 OFF

recorder : 모든 토픽 구독 → data/sessions/<session_id>.jsonl
           (데이터셋 · 지연 측정 · 재생 회귀 테스트에 공용)
```

## 2. 안전 계층

| 계층 | 위치 | 역할 | LLM 의존 |
|---|---|---|---|
| L0 | ESP32 펌웨어 | 온도 하드 리밋, Pi 하트비트 타임아웃 → 안전 상태 | 없음 |
| L1 | `safety_guard` (Pi) | Action 화이트리스트, 파라미터 범위, 현재 State 기준 위험 명령 REJECT, 과열·방치 시 자동 차단 | 없음 |
| L2 | `llm_svc` (Pi) | 자연어 → Function Call **제안**만 | — |

- 위험 감지(과열·방치)는 `fusion_svc` → `safety_guard` → `ble_gw`로 바로 간다. LLM 경로를 기다리지 않는다.
- 긴급 키워드("정지/멈춰/그만" 등)는 STT 결과에서 바로 EMERGENCY_STOP으로 연결한다 (빠른 경로).

## 3. 입력 개시 (호출어)

- v0: STT 결과 텍스트가 "자비스"로 시작할 때만 명령으로 처리. 나머지는 로그만 남기고 무시.
- 이후 검토: 전용 호출어 모델 (한국어 사전학습 모델 유무 확인 필요).

## 4. 프로세스 · 통신

- 모듈마다 별도 프로세스. 통신 방식은 [open-questions](../decisions/open-questions.md) Q-06에서 결정 (후보: 로컬 MQTT(mosquitto) / ZeroMQ / Python multiprocessing Queue).
- 어떤 방식이든 메시지는 [interfaces](./interfaces.md)의 봉투 형식을 따른다 → 나중에 방식을 바꿔도 모듈 코드는 그대로.

## 5. 시간 동기화

- 모든 `ts`는 **Orange Pi 한 대의 시계**로 찍는다 (수신 시각 기준). ESP32 센서값도 Pi가 받은 시각으로 기록.
- 지연 측정용 구간 계산은 단조 시계(monotonic) 값 `mono`를 별도 필드로 함께 기록.

## 6. NPU · 자원 배치 (초안, 측정 후 확정)

RK3588/RK3588S NPU: 6 TOPS, 3코어. 하드웨어 상세는 [hardware](./hardware.md).

| 작업 | 실행 장치 | 비고 |
|---|---|---|
| VAD, STT | CPU (기본) | sherpa-onnx RKNN 빌드로 NPU 실행 가능 (SenseVoice·Silero VAD 지원 확인). NPU 경합과 비교해 실측 후 결정 |
| YOLOv8n | NPU core0 | 3~5fps면 "방치" 판단에 충분 |
| LLM | NPU 나머지 코어 | RKLLM 변환 시 `num_npu_core`(최대 3)로 지정. 동시 구동 부하는 BOARD-08에서 측정 |
| 전처리·후처리(NMS) | CPU | 병목이 되기 쉬움 → 구간별 시간 측정 |

## 7. 주요 상태 (State Machine 초안)

`IDLE → PREHEAT → COOKING → (UNATTENDED) → DANGER → SAFE_STOP`
정의·전이 조건은 [interfaces](./interfaces.md) §2.3과 FUS 작업에서 확정.
