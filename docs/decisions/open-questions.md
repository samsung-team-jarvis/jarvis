# 결정 사항 (초기 결정 대기 질문)

착수 시점에 열어 둔 질문과 그 결정. 초기 계획은 임시안이었고, 2026-10-02 확인된 사실(공식 문서 검증, Mac·Docker 실행 결과, [학교 제공 자료](../school-materials.md))을 기준으로 확정했다.
여러 작업에 영향을 주는 결정은 [Decision Log](./index.md)에 별도 파일로 둔다. 비용이 드는 항목은 [budget](../budget.md)에 모은다.

상태: ✅ 확정 · ⏳ 정보 대기(무엇을 기다리는지 명시, 기다리는 동안의 기본값도 정함)

| ID | 질문 | 결정 | 상태 |
|---|---|---|---|
| Q-01 | 보드: Orange Pi 5인가 5 Plus인가, RAM은? | 학교 특강 기준 **Orange Pi 5 Plus · RK3588 · RAM 16GB · Ubuntu 22.04 배포 이미지**(RKNPU v0.9.8·음성 모델 사전 설치)로 안내됨 ([school-materials](../school-materials.md)). 문서는 이 기준으로 쓴다. 수령 시 BOARD-01에서 실물 확인(0절 3분 검증) | ⏳ 보드 수령 (기준은 확정) |
| Q-02 | 학사 일정(중간·최종 발표) | 날짜별 일정 대신 PLAN의 Phase·Gate로 진행한다. 발표 일정이 나오면 "발표 전 도달할 Gate"만 PLAN에 적는다 (예: 중간발표 = Gate 2 시연) | ⏳ 학교 공지 (진행에는 영향 없음) |
| Q-03 | 학습·변환용 x86 PC·GPU | LLM 학습·변환은 **학교 제공 클라우드 GPU 서버(A100) + 변환 도커(`run.sh`)** 를 기본으로 한다. YOLO 학습은 Colab 무료(`train_yolo.ipynb`). Colab RKLLM 노트북은 서버를 못 쓸 때의 대체. 💰 서버가 유료 대여인지는 확인 필요 ([budget](../budget.md)) | ✅ (서버 비용 여부 확인) |
| Q-04 | 역할 분담 | 작업물 4개 — ① 신지호 ② 이현종 ③ 최지환 ④ 최석진 ([decision](./2026-10-02-deliverables-split.md)) | ✅ |
| Q-05 | 마음AI SUDA 사용 여부 | SUDA 플랫폼 자체에 의존하지 않되, **SUDA 방식을 이식**한다: 함수 토큰 출력 형식(Q-10), docstring 함수 정의, 간접 발화·STT 오인식·숫자 표기 변형 데이터, 생성 프롬프트+키워드+어투로 데이터 구축, 차수별 개선 (학교 SUDA 데이터 시트 2종). 발표에는 "SUDA 데이터 구축·출력 형식을 주방 도메인에 이식"으로 서술 | ✅ |
| Q-06 | 모듈 간 통신 | 로컬 MQTT (mosquitto) ([decision](./2026-10-02-message-bus-mqtt.md)) | ✅ |
| Q-07 | LLM 후보 | LLM-06 Baseline 비교: **Llama-3.2-1B-Instruct**(학교 특강 예시 모델 — 도커·서버·예제 지원이 가장 확실), **Qwen3.5-2B**(특강의 한국어 비교 모델), **Qwen3-0.6B**(가장 빠름, RK3588 공식 벤치마크 32.2 tok/s 참고값). 선택 기준: 보드 Action Accuracy·형식 Valid Rate, tok/s ≥ 10, 메모리, E2E 지연. 결과로 decision log 작성 | ✅ (최종 모델은 LLM-06 측정으로) |
| Q-08 | 호출어 | v0: **STT 결과가 "자비스"로 시작할 때만** 명령으로 처리. 흔한 오인식 변형("자비스야", "쟈비스" 등)은 STT-05 녹음에서 확인해 허용 목록에 추가. 전용 호출어 모델은 오작동이 측정으로 확인될 때만 검토. **2026-10-02 갱신 (#57)**: 사람 음성 첫 확인에서 "다비스·바비스"로 받아써 명령 4건이 모두 무시됨 → 첫 글자가 자·다·바·차·짜·사·타 + "비스"를 호출로 허용 (근거·목록: [audio_svc](../../services/audio_svc/README.md#호출어)). 이후 조정은 STT-05 val 화자의 호출어 인식률·오호출로 한다 | ✅ |
| Q-09 | 비전 라벨링 도구 | **Roboflow 무료 플랜** 기본 (웹 GUI, 세트 분할, YOLOv8 zip export가 `train_yolo.ipynb` 입력 형식과 같음 → 코딩 없이 가능). 무료 플랜의 조건(데이터셋 공개 여부·이미지 수 한도)은 가입 시 확인 필요 — 공개 조건이면 **사람 얼굴이 찍히지 않게** 촬영한다. 조건이 맞지 않으면 무료·로컬인 Label Studio 또는 CVAT로 대체 | ✅ (조건 확인은 VIS-04 시작 시) |
| Q-10 | LLM 출력 형식 | **SUDA식 함수 토큰 형식**으로 출력시키고 `llm_svc`가 파싱해 interfaces §3의 Function Call(JSON)로 바꿔 버스에 발행한다. 예: `<jarvis_3>(target=hood, level=3)<jarvis_end>` (문법은 LLM-01에서 확정 → [interfaces](../architecture/interfaces.md) §3.2, [decision](./2026-10-02-function-call-schema.md)). 이유: JSON보다 출력 토큰이 적어 생성 지연이 줄고(소형 모델 tok/s가 낮음), 끝 토큰으로 생성 종료·캘리브레이션 절단(`calib_stop_at`)이 확실하다. 버스·Safety Guard가 보는 형식(JSON)은 바뀌지 않는다 | ✅ (문법 확정 #39) |
| Q-11 | 메타버스 플랫폼 | **Unity 6.3 LTS** (Unity Personal, 무료) ([decision](./2026-10-05-unity-virtual-kitchen.md)). 선택 기준 ① 보드와 메시지(Unity 안의 MQTT 클라이언트, MQTTnet 4.3.7) ② 인식용 카메라 화면 캡처(RenderTexture → JPEG) ③ 장치 상태 스크립트(C#) ④ 비용([budget](../budget.md))을 2026-10-05 공식 문서로 확인했다. 실제 동작은 HW-16·HW-20에서 확인한다 (그 전까지는 [simulator](../../services/simulator/README.md)의 가짜 메시지로 개발) | ✅ (실동작 미검증) |
| Q-12 | 보드 ↔ 가상 주방 연결 방식 | HW-14에서 확정. 기본 방향: 보드의 버스(MQTT) 메시지를 그대로 쓰고, 가상 주방(Unity) 쪽에 메시지를 주고받는 연결 부분만 둔다 ([interfaces](../architecture/interfaces.md) §4) | ⏳ HW-14 |
| Q-13 | 가상 온도 계산 규칙 | 가열 장치의 세기와 켜 둔 시간으로 오르내리게 한다. 수치(오르는 속도, 위험 구간)는 HW-19·FUS-05에서 정한다 | ⏳ HW-19·FUS-05 |
| Q-14 | 장치 8종의 세부 명령 | 장치: 화구(2)·튀김기·후드(환풍기와 같음)·조명·에어컨·선풍기·음악·결제시스템. 켜기·끄기·세기·타이머·상태 확인은 지금 Action에 target만 추가, 결제는 결제 요청·금액 확인 Action 추가. 값의 범위(에어컨 온도, 밝기, 음량)와 결제 확인 절차는 LLM-13에서 확정 | ⏳ LLM-13 |

## 문서 불일치 정리 (DOC-02)

이 저장소의 문서는 아래 통일안으로 이미 쓰여 있다. 다음 주간보고·발표자료(DOC-07, DOC-10)부터 같은 표현을 쓴다.

| 항목 | 수행계획서 | 5주차 발표자료 | 통일안 (확정) |
|---|---|---|---|
| 프로젝트명 · 대상 | 스마트 자영업 서비스 어시스턴스: 자비스 | 1인 주방 어시스턴트 | "혼자 가게를 운영하는 자영업자를 위한 온디바이스 음성 어시스턴트. 주방과 매장 장치 8종을 가상 주방에서 제어" (2026-10-05) |
| 보드 | Orange Pi 5 (RK3588S) | Orange Pi 5 Plus (RK3588) | "Orange Pi 5 계열 (RK3588, 6 TOPS NPU)" — 수령 후 실물 모델명으로 교체 |
| 언어 이해 | 오프라인 STT/NLU | VAD→STT→소형 LLM(Function Call) | "STT → 소형 LLM 명령 해석기(Function Call). LLM은 명령을 제안만 하고, 실행은 Safety Guard가 결정" |
| 비전 | 조리 동작/도구 감지 | 객체 Context (pan·burner·hand) | "객체 감지(YOLOv8n) + 시간 흐름으로 조리 상태 추론" — 동작 인식 모델은 쓰지 않는다 |
| STT 지표 | - | WER | CER(글자 오류율)을 주지표, STT→Action 정확도를 함께 (한국어는 띄어쓰기 때문에 WER이 왜곡됨) |
| 물리 차단 | 위험 시 물리 차단 | ESP32 직접 제어 | "가상 주방에서 가열 장치를 끄는 것으로 차단 시연" — 실물 장치는 다루지 않는다 (2026-10-05 [가상 주방 결정](./2026-10-05-virtual-kitchen-demo.md). 이전 통일안: 저전압 모형) |
| SUDA | SUDA 플랫폼 연동 검토 | (언급 없음) | "마음AI SUDA의 경량화·이식 방식을 참고" (Q-05) |
| LLM 모델 | (언급 없음) | Llama-3.2-1B | "소형 LLM 후보 3종 비교 후 선정" (Q-07) |
