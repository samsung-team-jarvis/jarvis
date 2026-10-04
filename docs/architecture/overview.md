# 시스템 아키텍처 (v0.2 초안)

> 2026-10-05 시연 환경을 **가상 주방(메타버스)** 으로 바꿨다 ([decision](../decisions/2026-10-05-virtual-kitchen-demo.md)). 실물 제어 하드웨어는 없다. 플랫폼은 미정이라, 가상 주방과 잇는 부분은 방향만 적었다.

## 1. 전체 흐름

```
[핀마이크(USB), 실제 음성] → audio_svc : Silero VAD → STT(SenseVoice, CPU) ──┐ stt/text
[가상 주방] ─캡처 화면→ vision_svc: YOLOv8n .rknn (NPU core0, 3~5fps) ────────┤ vision/objects
[가상 주방] ─가상 온도→ kitchen_gw : 온도 (1Hz) ──────────────────────────────┤ sensor/reading
                                                                              ▼
             ┌──────────── fusion_svc (State Machine + 현재 Context) ────────────┐
             │     stt/text + context ↓              ↑ llm/function_call         │
             │   llm_svc : 제공 FastAPI LLM 서버(RKLLM .rkllm, NPU)에 HTTP 요청   │
             │              (출력 파싱·검증, 실패 시 규칙 파서로 대체)            │
             └─────────────────────────────┬─────────────────────────────────────┘
                                           ▼
                 safety_guard : 화이트리스트 · 스키마 검증 · 위험 규칙 (결정론적)
                                           ▼ control/command (허용된 것만)
                 kitchen_gw → 가상 주방의 장치 (화구·튀김기·후드·조명·에어컨·선풍기·음악·결제)
                                           ← 결과 확인(seq) → control/result
                 가상 주방 자체 안전장치: 온도 상한 초과 또는 보드 생존 신호 끊김 → 가열 장치 OFF

                 guard/decision · fusion/state → audio_svc TTS(한국어 VITS, CPU) → 스피커
                 ("후드를 켰습니다", "기름 온도가 너무 높아요" 같은 음성 응답·경고)
                 fusion/state · stt/text · guard/decision → 가상 주방 화면에 겹쳐 띄우는 정보

recorder : 모든 토픽 구독 → data/sessions/<session_id>.jsonl
           (데이터셋 · 지연 측정 · 재생 회귀 테스트에 공용)
```

- **보드(Orange Pi)**: 음성 인식, 물체 인식, 명령 해석, 상황 인식, 안전 판단 — 추론은 모두 보드에서, 인터넷 없이 한다.
- **가상 주방(PC)**: 장면을 그리고, 인식용 카메라의 화면과 계산한 온도를 보드로 보내고, 보드의 제어 명령을 받아 장치를 바꾼다.
- `kitchen_gw`는 보드의 버스와 가상 주방을 잇는 서비스다 (이전 계획의 `ble_gw` 자리). 연결 방식은 플랫폼을 정한 뒤 확정한다 ([open-questions](../decisions/open-questions.md) Q-11·12).

## 2. 안전 계층

| 계층 | 위치 | 역할 | LLM 의존 |
|---|---|---|---|
| L0 | 가상 주방 (장치 스크립트) | 온도 상한, 보드 생존 신호 타임아웃 → 가열 장치를 끄는 안전 상태 | 없음 |
| L1 | `safety_guard` (보드) | Action 화이트리스트, 파라미터 범위, 현재 State 기준 위험 명령 REJECT, 과열·방치 시 자동 차단, 결제 요청은 확인 후 실행 | 없음 |
| L2 | `llm_svc` (보드) | 자연어 → Function Call **제안**만 | — |

- 위험 감지(과열·방치)는 `fusion_svc` → `safety_guard` → `kitchen_gw`로 바로 간다. LLM 경로를 기다리지 않는다.
- 긴급 키워드("정지/멈춰/그만" 등)는 STT 결과에서 바로 EMERGENCY_STOP으로 연결한다 (빠른 경로).
- 3계층 정책은 실물 모형 계획 때와 같다. L0의 위치만 ESP32 펌웨어에서 가상 주방으로 옮겼다 ([안전 3계층](../decisions/2026-10-01-safety-layers.md)).

## 3. 입력 개시 (호출어)

- v0: STT 결과 텍스트가 "자비스"로 시작할 때만 명령으로 처리. 나머지는 로그만 남기고 무시.
- 이후 검토: 전용 호출어 모델 (한국어 사전학습 모델 유무 확인 필요).

## 4. 프로세스 · 통신

- 모듈마다 별도 프로세스. 통신은 **로컬 MQTT(mosquitto)** ([decision](../decisions/2026-10-02-message-bus-mqtt.md)). MQTT 토픽 = 봉투의 `type`.
- 구현: [`common/`](../../common/) — `Envelope`(봉투), `connect()`(버스). 버스 주소는 `JARVIS_BUS` 환경변수 (`mqtt://localhost:1883` 기본, 테스트는 `memory://`).
- 어떤 방식이든 메시지는 [interfaces](./interfaces.md)의 봉투 형식을 따른다 → 나중에 방식을 바꿔도 모듈 코드는 그대로.
- 가상 주방은 보드 밖(PC)에 있다. 보드와 같은 네트워크에서 메시지를 주고받는다 (방식은 Q-12).

## 5. 시간 동기화

- 모든 `ts`는 **Orange Pi 한 대의 시계**로 찍는다 (수신 시각 기준). 가상 주방이 보낸 온도·화면도 보드가 받은 시각으로 기록.
- 지연 측정용 구간 계산은 단조 시계(monotonic) 값 `mono`를 별도 필드로 함께 기록.

## 6. NPU · 자원 배치 (초안, 측정 후 확정)

RK3588/RK3588S NPU: 6 TOPS, 3코어. 하드웨어 상세는 [hardware](./hardware.md).

| 작업 | 실행 장치 | 비고 |
|---|---|---|
| VAD, STT | CPU 4스레드 | 학교 특강 기본 배치. sherpa-onnx RKNN 빌드로 NPU 실행도 가능하지만 NPU는 LLM·YOLO가 쓰므로 CPU 유지 |
| TTS (한국어 VITS) | CPU 2스레드 | 음성 응답·경고. 재생 중에는 마이크 입력을 무시(에코 방지) |
| YOLOv8n | NPU (LLM과 공유) | 3~5fps면 "방치" 판단에 충분. 입력은 가상 주방의 캡처 화면. LLM이 3코어를 모두 쓰므로 **동시 구동 시 서로 느려지는 정도를 BOARD-08에서 측정**하고, 필요하면 LLM 생성 중 YOLO를 잠시 멈추거나 fps를 낮춘다 |
| LLM | NPU 3코어 | 학교 도커 기준 `num_npu_core: 3` 전 팀 고정. 제공 FastAPI 서버로 서빙 |
| 전처리·후처리(NMS) | CPU | 병목이 되기 쉬움 → 구간별 시간 측정 |
| 가상 주방 (장면 그리기) | 보드 밖의 PC | 보드 자원을 쓰지 않는다 |

## 7. 주요 상태 (State Machine 초안)

`IDLE → PREHEAT → COOKING → (UNATTENDED) → DANGER → SAFE_STOP`
정의·전이 조건은 [interfaces](./interfaces.md) §2.3과 FUS 작업에서 확정.
