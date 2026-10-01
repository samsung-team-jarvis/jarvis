# JARVIS — 온디바이스 스마트 주방 어시스턴트

2026-2 모바일시스템응용프로젝트(산학협력) 삼성팀 프로젝트.
1인 주방에서 음성·비전·온도/전류 센서를 Orange Pi(RK3588 NPU)에서 오프라인으로 융합 추론하고,
State Machine + Safety Guard를 거쳐 ESP32(BLE)로 장비(모형)를 제어한다.

- 원본 기획: `../[N]5팀(삼성) 산학협력프로젝트 수행계획서.docx`, 5주차 발표자료(`~/Downloads/삼성팀_JARVIS_5주차_발표.pdf`)
- 산업체 멘토: 마음AI (SUDA 플랫폼 — 사용 가능 여부 미확인)

## 문서 지도 (작업 전 반드시 해당 문서부터 읽을 것)

| 문서 | 내용 | 언제 갱신 |
|---|---|---|
| `docs/PLAN.md` | 해야 할 작업 백로그 (Phase·워크스트림별, 완료 기준 포함) | 작업 시작/완료 시 체크박스·담당 갱신 |
| `docs/ARCHITECTURE.md` | 시스템 구조, 안전 계층, 프로세스·NPU 배치 | 구조가 바뀔 때 |
| `docs/INTERFACES.md` | 메시지 봉투·토픽·Function Call 스키마·BLE 패킷 | 규격 변경 시 (변경 이력 필수) |
| `docs/DECISIONS.md` | 확정된 결정(ADR)과 결정 대기 질문 | 결정이 나거나 바뀔 때 |
| `docs/METRICS.md` | 평가 지표 정의·측정 방법·실측 결과 | 측정할 때마다 |

## 작업 원칙

1. **Walking Skeleton 우선.** 새 기능은 "끝까지 연결된 가장 단순한 버전"이 동작한 뒤에 고도화한다. 통합되지 않은 모듈의 완성도를 올리는 작업보다 E2E 연결을 우선한다.
2. **인터페이스 먼저.** 모듈 간 주고받는 데이터는 `docs/INTERFACES.md`에 정의된 형식만 쓴다. 규격에 없는 필드가 필요하면 문서를 먼저 고친다.
3. **측정값은 실측만.** 수치를 추정·가정해서 문서나 발표자료에 쓰지 않는다. 미측정은 `측정 예정`으로 남긴다. 실측값은 측정 일시·보드·모델/툴 버전·데이터셋·커밋을 함께 기록한다. 최종 수치는 **보드(Orange Pi) 기준**.
4. **안전 규칙 (위반 금지)**
   - LLM 출력은 절대 직접 장비를 제어하지 않는다. 반드시 Safety Guard(결정론적 규칙)를 통과한다.
   - 과열·방치 같은 위험 감지 경로는 LLM을 거치지 않는다.
   - ESP32 펌웨어는 Pi와 무관하게 동작하는 자체 안전장치(온도 상한, 하트비트 타임아웃 → 안전 상태)를 가진다.
   - 실물 가스·220V 배선을 제어/계측하지 않는다. 제어 대상은 저전압 모형(LED·USB팬·부저·릴레이)만.
5. **버전 고정.** RKNN-Toolkit2 / rknn-toolkit-lite2 / RKNPU 런타임 / RKLLM toolkit·runtime / NPU 드라이버 버전은 `docs/DECISIONS.md`의 버전 표에 고정된 값만 쓴다. 변환 툴 버전과 보드 런타임 버전 불일치가 가장 흔한 실패 원인이다.
6. **확실하지 않은 기술 정보는 "(확인 필요)"로 표시**하고, 공식 문서(airockchip/rknn-toolkit2, rknn_model_zoo, rknn-llm, sherpa-onnx 등)로 확인한 뒤 지운다.

## 개발 환경 제약

- 개발 PC: **M1 Pro Mac (arm64, 16GB)**.
  - Mac에서 가능: sherpa-onnx STT 실험, ultralytics 추론·라벨링, 스크립트 개발, 서비스 로직(모의 데이터).
  - Mac에서 불가/비권장: rkllm-toolkit 변환(x86_64 Linux 전용으로 알려짐, 확인 필요), LLM LoRA 학습 → **Colab(x86 + GPU)** 사용.
  - ONNX→RKNN 변환: Colab(x86 Linux) 또는 보드(aarch64 휠, 확인 필요).
- 보드: Orange Pi 5 / 5 Plus (RK3588(S), NPU 3코어) — 모델·RAM 미확정 (`docs/DECISIONS.md` Q-01).
- 언어: Python 3.10+ (서비스), C/C++ (필요 시 성능 경로), Arduino/ESP-IDF (ESP32).

## 저장소 구조 (목표)

```
jarvis/
├─ docs/            # 계획·규격·결정·지표
├─ common/          # 메시지 스키마, 버스 래퍼, 로거 (팀 공통)
├─ services/        # audio_svc, vision_svc, llm_svc, fusion_svc, safety_guard, ble_gw, recorder
├─ firmware/esp32/
├─ training/        # yolo/, llm/ (Colab 노트북), stt_eval/
├─ data/            # 원본 데이터는 git 제외(Drive), 매니페스트·split 파일만 커밋
└─ bench/           # 지연·정확도 측정 스크립트 → docs/METRICS.md 갱신
```

## 협업 규칙

- 브랜치: `main` 보호, 작업은 `feat/<워크스트림>-<짧은설명>` (예: `feat/stt-cer-eval`).
- 커밋 메시지: `[워크스트림] 요약` (예: `[VIS] RKNN INT8 변환 스크립트 추가`). 커밋에 Co-Authored-By 푸터를 넣지 않는다.
- 모델 가중치(`*.pt`, `*.onnx`, `*.rknn`, `*.rkllm`)와 원본 데이터(wav, jpg, mp4)는 커밋하지 않는다.
- 작업을 끝내면 `docs/PLAN.md`의 해당 항목 체크 + 완료 기준 충족 근거(커밋/측정 결과 링크)를 남긴다.

## Claude에게

- 사용자는 온디바이스/임베디드 분야가 처음이다. 새 개념(NPU, 양자화, 캘리브레이션, chat template 등)이 나오면 한두 줄로 설명하고 진행한다.
- 작업 지시가 오면 `docs/PLAN.md`에서 해당 작업 ID를 찾아 완료 기준을 확인하고 시작한다. 계획에 없는 작업이면 PLAN에 먼저 추가할지 묻는다.
- 응답과 문서는 한국어로 작성한다.
