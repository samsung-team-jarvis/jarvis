# 작업 계획 (Backlog)

> 날짜별·주차별 일정은 두지 않는다. **Phase 순서대로** 진행하고, 한 Phase의 **관문(Gate)** 을 통과해야 다음 Phase의 핵심 작업으로 넘어간다.
> 같은 Phase 안의 작업은 선행 조건만 지키면 병렬로 진행해도 된다.

## 사용법

- 항목 형식: `- [ ] ID 작업 — 완료 기준 | 선행: ID | 담당: 미정`
- 작업 시작 = GitHub 이슈 생성 (제목 `[ID] 작업 요약`, 본문에 완료 기준 복사). 이후 흐름은 [Git Convention](./conventions/git.md).
- 작업 시작 시 `담당`에 이름과 이슈 번호를 적고, 완료 시 `[x]` 체크 + 근거(PR 번호, `docs/METRICS.md` 항목 등)를 덧붙인다.
- 진행 중이 아니게 된 작업은 담당을 다시 `미정`으로 돌린다.
- 새 작업이 생기면 해당 워크스트림 끝에 다음 번호로 추가한다. 번호는 재사용하지 않는다.

## 작업물과 담당

팀원마다 **입력 → 출력이 분명한 작업물 하나**를 처음부터 끝까지(데이터 → 모델/코드 → 보드 → 측정) 맡는다. 작업물 사이의 경계는 [interfaces](./architecture/interfaces.md)의 토픽이고, 각 작업물의 성과는 [METRICS](./METRICS.md)의 해당 지표로 보인다. 결정 근거: [decision log](./decisions/2026-10-02-deliverables-split.md)

| 작업물 | 담당 | 입력 → 출력 | 주요 작업 ID | 대표 지표 |
|---|---|---|---|---|
| ① 비전 데이터·모델 + 보드 + 팀 운영 | **신지호** | 카메라 → 학습·변환된 비전 모델(`.rknn`) | BOARD-01~04·09, VIS-01~07·09, DOC-01~03·05·07·10 | mAP50, 양자화 전후 mAP |
| ② 음성 → 명령 AI 서비스 + 공통 런타임 | **이현종** | 음성 → Function Call(JSON) / 서비스 실행 기반 | STT-*, LLM-*, INFRA-03~06·08, BOARD-05~08, VIS-08·10, FUS-02·06, UI-*(선택) | CER, Action Acc, JSON Valid, E2E 지연, NPU 동시 부하 |
| ③ 상황 인식 + 안전 | **최지환** | 음성·비전·센서 → 주방 상태·위험 판단·차단 명령 | FUS-01·03~05·07~11, INFRA-07 | State F1, 위험 미탐율, 감지→차단 지연 |
| ④ 제어 하드웨어 + 모형 | **최석진** | 제어 명령 → 장치 동작 / 센서 → 측정값 | HW-*, DOC-04·06 | BLE 성공률·지연, 하트비트 안전 정지 |

- ①은 **코딩을 최소화**하도록 짰다: 촬영·라벨링(GUI 도구), Colab 노트북 실행(학습·변환), recipe 명령 실행(보드), 제공된 측정 스크립트 실행. 노트북·스크립트는 ②가 만든다 (VIS-10, BOARD-06).
- ①의 모델을 서비스로 감싸는 코드(VIS-08 `vision_svc`)와 NPU 동시 부하 측정(BOARD-08)은 ②가 맡는다.
- 공동: INFRA-02(규칙 동의), INFRA-09(정기 통합, ② 주관), DOC-08·09(최종 보고서·리허설).

워크스트림 코드(라벨·작업 ID 접두사): INFRA 공통 · BOARD 보드·NPU · STT 음성 · VIS 비전 · LLM 명령 해석 · FUS 상황 인식·안전 · HW 하드웨어 · UI 대시보드 · DOC 문서·발표

---

## Phase 0 — 착수 준비 (결정·환경·규격)

**Gate 0:** `docs/decisions/open-questions.md`의 질문이 모두 확정 또는 정보 대기(사유 명시) · `docs/conventions/versions.md` 고정 · `docs/architecture/interfaces.md` v0.1 팀 합의 · 부품 주문 완료

- [ ] INFRA-01 GitHub 저장소 생성, 팀원 초대, `main` 보호, 이 harness(CLAUDE.md·docs) 푸시 — 4명 모두 clone 성공 | 선행: - | 담당: 이현종 (#7, 팀원 온보딩 진행 중)
- [ ] INFRA-02 `.gitignore`(가중치·원본 데이터 제외), 브랜치·커밋 규칙 공유 — CLAUDE.md 협업 규칙에 모두 동의 | 선행: INFRA-01 | 담당: 공동
- [x] INFRA-10 컨벤션 자동 검사 (커밋·브랜치·PR 형식 훅과 CI, AI 도구 guard hook, 브랜치 보호 필수 체크) — 틀린 형식이 로컬·CI에서 실패 | 선행: INFRA-02 | 담당: 이현종 (#4 → PR #5)
- [x] INFRA-11 원커맨드 개발 환경(`scripts/setup.py`)과 온보딩 문서 — 새 clone에서 한 번에 훅 설치·검사 통과 | 선행: INFRA-10 | 담당: 이현종 (#6)
- [x] INFRA-12 팀원 작성자 라벨과 자동 리뷰어 지정(CODEOWNERS) — PR 생성 시 리뷰 요청 자동 생성 | 선행: INFRA-11 | 담당: 이현종 (#9 → PR #10. 2026-10-02 리뷰 요청 메일 부담으로 CODEOWNERS 제거, 라벨만 유지 — #42)
- [x] DOC-01 결정 대기 질문 Q-01~Q-08 답변 수집 (`docs/decisions/open-questions.md`) — 각 질문에 답 또는 "보류 사유" 기재 | 선행: - | 담당: 신지호 (#23, 이현종 대행)
- [x] DOC-02 수행계획서·발표자료 불일치 정리 (Orange Pi 5 vs 5 Plus, STT/NLU vs 소형 LLM 표현, "조리 동작 감지" → "물체+시간 기반 상태 추론", WER→CER 병기) — 수정 목록을 open-questions에 기록 | 선행: DOC-01 | 담당: 신지호
- [x] DOC-11 기술 스택·문서 사실 검증 — recipe·환경·버전 문서의 "(확인 필요)"를 공식 자료로 확인하고 출처 기록 | 선행: - | 담당: 이현종 (#11)
- [x] INFRA-13 대용량 파일 공유: 직접 전달 + 산출물 등록부(`docs/artifacts.md`, `scripts/artifact_info.py`), 노트북 Drive 의존 제거 — 저장소에 Drive 경로 없음 | 선행: - | 담당: 이현종 (#27)
- [x] DOC-12 학교 제공 자료(마음AI 특강2·SUDA 데이터 시트) 반영 — 문서가 학교 환경·방식과 충돌하지 않음 | 선행: - | 담당: 이현종 (#25)
- [x] DOC-13 README 정리 — 루트 README에 동작 흐름·구성·빠른 시작·폴더 구조, 서비스 README는 사용법 → 동작 → Spec → 확인 기록 순 | 선행: - | 담당: 이현종 (#68)
- [ ] DOC-03 마음AI 멘토 질문 전달 (SUDA 사용 가능 범위, 한국어 STT 추천 모델, RK3588 양자화 경험) — 답변 open-questions에 기록 | 선행: - | 담당: 신지호
- [x] FUS-01 메시지 봉투·토픽·State 열거형 v0.1 검토·합의 (`docs/architecture/interfaces.md`) — 4명 합의 표시 | 선행: - | 담당: 최지환 (#39 — 2026-10-02 결정권자 확정·팀 통보, 상황 인식 구현 중 변경 가능)
- [x] LLM-01 Function Call 스키마 v0.1 확정 (Action 10개, target 목록, 파라미터 범위) — interfaces §3 확정 | 선행: FUS-01 | 담당: 이현종 (#39, `common/function_call.py`)
- [ ] HW-01 BLE GATT·패킷 규격 v0.1 확정 — interfaces §4 확정 | 선행: FUS-01 | 담당: 최석진
- [ ] HW-02 부품 목록(BOM) 확정·주문 — 아래 BOM 표 기준, 수량·구매처 기록 | 선행: - | 담당: 최석진
- [ ] BOARD-01 보드 실물 확인 (모델, RAM, 저장장치, 방열판·팬 유무) — open-questions Q-01 답변 | 선행: - | 담당: 신지호

### BOM (초안)

구매·무료 대안·유료 서비스 정리: [budget](./budget.md)

| 품목 | 용도 | 비고 |
|---|---|---|
| Orange Pi 5 / 5 Plus + 전원 어댑터 + **방열판·팬** | 메인 추론 | 주방 환경·장시간 구동이라 방열 필수. 두 보드 차이: [hardware](./architecture/hardware.md) |
| microSD 또는 NVMe/eMMC | OS·모델 저장 | 모델 여러 개 보관 → 64GB 이상 권장 |
| USB 웹캠 (UVC) | 비전 입력 | MIPI 카메라보다 드라이버 이슈 적음 |
| USB 핀마이크 또는 USB 사운드카드 + 핀마이크 | 음성 입력 | 웹캠 내장 마이크와 비교 측정 예정 |
| 소형 스피커 (USB 또는 3.5mm) | TTS 음성 응답·경고 | STT-12 |
| ESP32 DevKit × 1~2 | 제어·센서 단말 | |
| **Bluetooth 모듈 또는 USB BT 동글 (보드용)** | Pi ↔ ESP32 BLE | Orange Pi 5 / 5 Plus 모두 기본 BT 없음. 호환 모델은 보드 수령 후 확인 |
| **K타입 열전대 + MAX31855** | 고온 측정 | DS18B20은 125°C 한계라 조리 온도 불가, MAX6675는 단종 정보가 있어 비권장 ([hardware](./architecture/hardware.md)) |
| INA219 | DC 부하 전류 측정 | 220V 계측 금지 |
| 릴레이 모듈(저전압), LED, USB 팬, 부저 | 화구·후드·알림 모형 | |
| 브레드보드·점퍼·저항 | 배선 | |

---

## Phase 1 — Hello World (각 모듈 단독 동작)

**Gate 1:** 아래 5개가 각각 단독으로 시연 가능 — ① 보드에서 기본 YOLOv8 RKNN 예제 실행 ② 보드에서 RKLLM 기본 모델 대화 ③ SenseVoice 한국어 받아쓰기 ④ ESP32 BLE 에코 + LED 제어 ⑤ 버스로 가짜 메시지 송수신

- [ ] BOARD-02 OS 설치(공식 Ubuntu 이미지), SSH·원격 개발 환경 — Mac에서 SSH 접속, VS Code Remote 동작 | 선행: BOARD-01 | 담당: 신지호
- [ ] BOARD-03 NPU 드라이버 버전 확인, RKNN·RKLLM 툴/런타임 버전 조합 결정 → `docs/conventions/versions.md` 고정 | 선행: BOARD-02 | 담당: 신지호
- [ ] BOARD-04 `rknn_model_zoo` YOLOv8 예제를 보드에서 실행 (기본 모델) — 이미지 1장 추론 결과 확인 | 선행: BOARD-03 | 담당: 신지호
- [ ] BOARD-05 RKLLM 데모를 지원 모델 1개로 보드에서 실행 (학교 도커 `run.sh build-demo`의 `llm_demo`, 클럭 고정 후) — 한국어 질의 1건 응답, tok/s 메모 | 선행: BOARD-03 | 담당: 이현종
- [ ] BOARD-06 Colab에서 rkllm-toolkit·rknn-toolkit2 설치 노트북 — 변환 1회 성공 | 선행: BOARD-03 (보드 미수령으로 최신 릴리스 기준 선진행) | 담당: 이현종 (#13) — RKNN 변환 성공(Docker amd64), RKLLM은 Colab 실행 대기
- [x] INFRA-03 `common/` 메시지 봉투 dataclass + 버스 래퍼 (Q-06 결정 방식) — 가짜 publisher/subscriber 예제 동작 | 선행: FUS-01 (v0.1 초안 기준 선진행) | 담당: 이현종 (#20)
- [x] INFRA-04 가짜 메시지 생성기 (stt/vision/sensor 모의) — 다른 모듈 없이 각 서비스 개발 가능 | 선행: INFRA-03 | 담당: 이현종 (#29, `services/simulator`)
- [x] STT-01 Mac에서 sherpa-onnx + SenseVoice-Small 한국어 wav 받아쓰기 — 결과 텍스트 출력 | 선행: - | 담당: 이현종 (#33, `services/audio_svc`)
- [ ] STT-02 보드에서 동일 STT 실행 — RTF(처리시간/음성길이) 메모 | 선행: STT-01, BOARD-02 | 담당: 이현종
- [ ] VIS-01 Mac에서 ultralytics 기본 YOLOv8n으로 주방(또는 유사) 영상 추론 — 기본 COCO 클래스로 잡히는 것 목록화 | 선행: - | 담당: 신지호
- [ ] HW-03 ESP32 BLE 서버 (cmd write / ack notify) — Pi 또는 Mac의 `bleak`으로 LED on/off | 선행: HW-01 | 담당: 최석진
- [ ] HW-04 열전대(MAX31855)·INA219 값 시리얼 출력 — 실온·뜨거운 물로 온도 변화 확인 | 선행: HW-02 | 담당: 최석진

---

## Phase 2 — Walking Skeleton (말 → LED, 끝까지 연결)

**Gate 2:** "자비스, 후드 켜줘" 발화 → STT → 규칙 파서 → Safety Guard → BLE → ESP32 LED 점등이 보드에서 동작하고, 전 구간 지연이 레코더 로그로 측정됨

- [x] STT-03 `audio_svc` v0: 마이크 → Silero VAD → SenseVoice → `stt/text` 발행 | 선행: STT-02, INFRA-03 (보드 미수령으로 Mac 기준 선진행) | 담당: 이현종 (#35 — wav·MQTT 확인, 2026-10-02 MacBook 마이크로 사람 음성 확인 #57)
- [x] STT-04 텍스트 기반 호출어 v0: "자비스"로 시작하는 발화만 명령 처리 — 비호출 발화는 무시 로그 | 선행: STT-03 | 담당: 이현종 (#37, `services/audio_svc/wake.py`)
- [ ] STT-12 TTS 음성 응답 v0: `guard/decision`·위험 경고를 한국어 VITS(sherpa-onnx, 배포 이미지 제공 모델)로 읽어 줌, 재생 중 마이크 입력 무시 — "자비스 후드 켜줘" → "후드를 켰습니다" | 선행: STT-03 | 담당: 이현종 (#51 — 응답·무음 처리 구현, wav 저장으로 확인. 스피커 재생·실제 에코 차단 확인 대기)
- [x] FUS-02 규칙 기반 파서 v0 (키워드 → Function Call) — Action 10개 중 최소 TURN_ON/TURN_OFF/EMERGENCY_STOP | 선행: LLM-01 | 담당: 이현종 (#41, `services/llm_svc` — 10개 모두)
- [ ] FUS-03 `safety_guard` v0: 화이트리스트·스키마 검증, 위험 상태에서 REJECT — 단위 테스트 통과 | 선행: LLM-01 | 담당: 최지환
- [ ] FUS-04 긴급 빠른 경로: "정지/멈춰/그만" 등은 LLM 없이 즉시 EMERGENCY_STOP | 선행: FUS-03 | 담당: 최지환
- [ ] HW-05 `ble_gw` 서비스: 버스 `control/command` → BLE write, ACK(seq) 수신·재시도, `control/result` 발행 | 선행: HW-03, INFRA-03 | 담당: 최석진
- [ ] HW-06 ESP32 하트비트 감시: Pi 하트비트 N초 끊기면 모든 출력 OFF | 선행: HW-03 | 담당: 최석진
- [x] INFRA-05 `recorder`: 모든 토픽을 세션별 JSONL로 저장 | 선행: INFRA-03 | 담당: 이현종 (#31, `services/recorder`)
- [x] INFRA-06 지연 분해 스크립트: 발화 끝 → STT → 파서 → Guard → BLE ACK 구간별 ms — METRICS E2E 항목 첫 기록 | 선행: INFRA-05 | 담당: 이현종 (#45, `bench/latency.py` — 첫 기록은 Mac·명령 발행까지, Guard·BLE 구간은 해당 서비스가 생기면 같은 명령으로)
- [x] BOARD-07 서비스 일괄 기동/종료 스크립트 (systemd 또는 단일 런처) | 선행: INFRA-03 | 담당: 이현종 (#47, `scripts/launch.py` — Mac 확인, systemd 예시는 보드 미검증)
- [ ] DOC-04 Skeleton 시연 영상 1편 녹화 | 선행: Gate 2 항목 전부 | 담당: 최석진

---

## Phase 3 — 데이터 수집 · Baseline 측정

**Gate 3:** `docs/METRICS.md`의 모든 Baseline 칸이 실측값으로 채워짐 (LLM은 기본 모델+프롬프트, 규칙 파서 포함)

### 데이터
- [ ] STT-05 STT 테스트 세트: 명령 발화 대본 작성 + 화자 4~6명 × 소음 4종(quiet/hood/frying/mixed) 녹음, `speaker_id` 기록 | 선행: LLM-01 | 담당: 이현종 (#53 — 대본 40문장·녹음 도구·안내 완료. 녹음: spk01 val quiet 40/40 MacBook 마이크 — 나머지 화자·소음 진행)
- [x] STT-06 CER·RTF·STT→Action 정확도 측정 스크립트 (`jiwer`) | 선행: STT-05 (녹음 전 선진행, 합성 음성으로 동작 확인) | 담당: 이현종 (#49, `bench/stt_eval.py`)
- [ ] VIS-02 클래스 정의 확정 (COCO 기본 클래스로 해결되는 것 제외, 7개 내외) — interfaces §2 반영 | 선행: VIS-01 | 담당: 신지호
- [ ] VIS-03 모형 주방 촬영 1차 (세션별 조명·각도·배치 변화, `session_id` 기록) ~200장 | 선행: VIS-02, HW-07 | 담당: 신지호
- [ ] VIS-04 라벨링 1차 (Roboflow 또는 CVAT), 세션 단위 split 파일 | 선행: VIS-03 | 담당: 신지호
- [x] VIS-10 Colab YOLO 학습·평가 노트북 템플릿 (데이터 경로·클래스만 바꾸면 학습 → mAP 평가 → ONNX export까지) — ①이 코드 수정 없이 VIS-06·07 실행 가능 | 선행: VIS-02 | 담당: 이현종 (#19)
- [ ] LLM-02 Seed 명령 500~800건 작성 (Action별 분포 목표 포함, **간접 발화**·**숫자 표기 변형**("3번"/"삼 번") 포함 — SUDA 방식, [school-materials](./school-materials.md)) | 선행: LLM-01 | 담당: 이현종 (#55 — 기획 시트로 627건 생성, 사람 검수 대기)
- [ ] LLM-03 Hard Negative 작성 (위험 상황 명령, 모호 발화, 지원 외 요청, 대명사·생략) | 선행: LLM-01 | 담당: 이현종 (#55 — 84건 생성, 사람 검수 대기)
- [ ] LLM-04 Paraphrase 합성 → 형식 검증·중복 제거·사람 검수 파이프라인 (6단계, 발표 p.9). 생성은 SUDA식 **기획 시트**(기능별 키워드 목록 + 어투 3종 + 데이터 비율 + 생성 프롬프트)로 | 선행: LLM-02 | 담당: 이현종 (#63 — 데이터 v1 2,234건, 사람 검수 대기)
- [x] LLM-05 템플릿·세션 단위 Train/Val/Test 분할, Test 고정, 캘리브레이션 세트는 Train에서만 | 선행: LLM-04 | 담당: 이현종 (#65, `training/llm/split_dataset.py` — 검수로 데이터가 바뀌면 같은 명령으로 재분할)
- [ ] FUS-05 센서 시나리오 20~30개 정의 (정상·과열·방치·화구 켜짐 방치) + 기록 — 하드웨어 전에는 [simulator](../services/simulator/README.md) 시나리오 형식으로 먼저 작성 | 선행: HW-04 | 담당: 최지환
- [ ] HW-07 모형 1차 (화구 LED·후드 팬·부저, 열전대 장착 위치) — 촬영 가능한 상태 | 선행: HW-02 | 담당: 최석진

### Baseline 측정 (모두 보드 기준)
- [ ] STT-07 SenseVoice 기본 설정 Baseline (CER by 소음 조건, RTF) | 선행: STT-06 | 담당: 이현종
- [ ] STT-08 비교군 Whisper(small/base) 측정 — STT 모델 결정 decision log 작성 | 선행: STT-06 | 담당: 이현종
- [ ] STT-09 마이크 비교 (핀마이크 vs 웹캠 내장) CER | 선행: STT-06 | 담당: 이현종
- [ ] VIS-05 기본 YOLOv8n Baseline (mAP50, P/R) + 보드 지연(전처리/NPU/후처리 분리) | 선행: VIS-04, BOARD-04 | 담당: 신지호
- [ ] LLM-06 LLM 후보 2~3개 (Llama-3.2-1B / Qwen2.5-0.5B·1.5B 등, RKLLM 지원 목록 확인) 프롬프트·few-shot Baseline — Action Acc, JSON Valid, Unsafe Rate, tok/s, RAM | 선행: LLM-05, BOARD-05 | 담당: 이현종
- [ ] FUS-06 규칙 파서 Baseline (LLM과 같은 Test Set) | 선행: LLM-05, FUS-02 | 담당: 이현종
- [ ] FUS-07 단일 조건 판단 Baseline (State F1, 위험 미탐율) | 선행: FUS-05 | 담당: 최지환
- [ ] HW-08 BLE 제어 Baseline (성공률, 왕복 지연) — 단순 전달 vs ACK·재시도 | 선행: HW-05 | 담당: 최석진

---

## Phase 4 — v1 모델 & 통합

**Gate 4:** 실제 모델(STT·YOLO RKNN·LLM .rkllm)이 Skeleton에 들어가 동시에 구동되고, 동시 구동 시 지연·RAM·온도가 측정됨

- [ ] VIS-06 YOLOv8n 파인튜닝 v1 (Colab) | 선행: VIS-04, VIS-10 | 담당: 신지호
- [ ] VIS-07 ONNX → RKNN INT8 변환 (실제 주방 이미지로 캘리브레이션), fp32/ONNX/INT8 mAP 비교 | 선행: VIS-06, BOARD-06 | 담당: 신지호
- [ ] VIS-08 `vision_svc`: 3~5fps 추론 → `vision/objects` 발행, 후처리 최적화 | 선행: VIS-07, INFRA-03 | 담당: 이현종
- [ ] LLM-07 LoRA/QLoRA v1 학습 (Colab), chat template·eos 고정 | 선행: LLM-05 | 담당: 이현종
- [ ] LLM-08 fp16 병합 → rkllm-toolkit W8A8 변환 → 보드 측정 (서버 기본/서버 학습/보드 양자화 3단계 비교) | 선행: LLM-07, BOARD-06 | 담당: 이현종
- [ ] LLM-09 `llm_svc`: `stt/text`+context → Function Call JSON, 검증 실패 시 규칙 파서 대체 | 선행: LLM-08, FUS-02 | 담당: 이현종
- [ ] FUS-08 State Machine v1 (센서+비전+음성 evidence 결합, stale context 만료) → `fusion/state` 발행 | 선행: FUS-05, VIS-08 | 담당: 최지환
- [ ] FUS-09 위험 감지 경로 (과열·방치) — LLM 무관, 감지→차단 지연 측정 | 선행: FUS-08 | 담당: 최지환
- [ ] HW-09 ESP32 자체 하드 리밋 (온도 상한 → 출력 OFF, Pi 무관) | 선행: HW-04 | 담당: 최석진
- [ ] HW-10 센서값 BLE notify → `ble_gw` → `sensor/reading` | 선행: HW-05, HW-04 | 담당: 최석진
- [ ] BOARD-08 NPU 코어 배치 (YOLO core0 / LLM 나머지) 및 동시 구동 부하 측정 (tok/s 변화, fps, RAM, SoC 온도) | 선행: VIS-08, LLM-09 | 담당: 이현종
- [ ] BOARD-09 장시간(30분+) 구동 발열·스로틀링 확인 | 선행: BOARD-08 | 담당: 신지호

---

## Phase 5 — 오류 분석 · 개선 사이클 (반복)

**Gate 5:** 최소 1회 이상 "오류 분석 → 데이터 보강 → 재학습 → 같은 Test Set 재평가" 사이클을 완료하고, 전후 수치가 METRICS에 기록됨

> 절차 (발표 p.14): Baseline 측정 → 오류 로그 수집 → 오류 유형 분류 → 데이터 추가·정제 → 재학습·재포팅 → 동일 Test Set 재평가. **Validation으로 분석, Test는 고정.**

- [ ] LLM-10 Validation 오류 유형 분류표 (환각 Action, 잘못된 target, 대명사 실패, 안전 위반 등) | 선행: LLM-08 | 담당: 이현종
- [ ] LLM-11 2차 데이터 보강 + LoRA v2 → 재변환 → 재평가 | 선행: LLM-10 | 담당: 이현종
- [ ] LLM-12 대화 문맥(last_target·State)을 구조화 context로 제공 → Context Test Acc | 선행: LLM-09, FUS-08 | 담당: 이현종
- [ ] STT-10 STT 오인식 패턴 수집 → 정규화 규칙 / LLM 학습 데이터 반영 (STT 오류 섞인 입력) | 선행: STT-07 | 담당: 이현종 (#61 — spk01 val 기반 첫 사전, `services/llm_svc/stt_fixes.py`)
- [ ] STT-11 소음 대응 개선 (DSP 전처리, 마이크 게인, VAD 임계값) → 재측정 | 선행: STT-07 | 담당: 이현종
- [ ] VIS-09 부족 클래스·조명 조건 보강 촬영 → v2 학습·변환·재평가 | 선행: VIS-07 | 담당: 신지호
- [ ] FUS-10 통합 멀티모달 시나리오 20~30개 녹화 (recorder) → State F1·위험 미탐율 | 선행: FUS-08, INFRA-05 | 담당: 최지환
- [ ] FUS-11 recorder 로그 재생 테스트 (녹화 세션을 다시 흘려 State Machine 회귀 테스트 — `services.recorder.store.read_session`으로 읽기) | 선행: FUS-10 | 담당: 최지환
- [ ] HW-11 BLE 성공률·지연 개선 (재시도 정책, 연결 끊김 복구) | 선행: HW-08 | 담당: 최석진
- [ ] HW-12 모형 완성 (발표 시연용) | 선행: HW-07 | 담당: 최석진
- [ ] UI-01 (선택) 로컬 대시보드 백엔드: 버스 구독 → WebSocket으로 상태·이벤트 전달 (FastAPI, 오프라인) | 선행: Gate 4 | 담당: 이현종
- [ ] UI-02 (선택) 대시보드 화면: 현재 상태·타이머·위험 경고·판단 근거(evidence) 실시간 표시 — 시연에서 "AI가 왜 그렇게 판단했는지" 보여주기 | 선행: UI-01 | 담당: 이현종

---

## Phase 6 — 기능 동결 · 최종 측정 · 발표

**Gate 6:** METRICS 최종 표 완성 (모두 보드·고정 Test Set) · 시연 영상 백업 · 최종 발표자료·보고서 제출

- [ ] DOC-05 기능 동결 선언 (이후 버그 수정만) | 선행: Gate 5 | 담당: 신지호
- [ ] INFRA-07 전체 시나리오 회귀 테스트 체크리스트 실행 | 선행: DOC-05 | 담당: 최지환
- [ ] INFRA-08 최종 측정 일괄 스크립트 실행 → METRICS 최종 표 | 선행: DOC-05 | 담당: 이현종
- [ ] DOC-06 시연 영상 백업 촬영 (정상 조리·음성 제어·과열 차단·방치 경고·LLM 거부 사례) | 선행: DOC-05 | 담당: 최석진
- [ ] DOC-07 최종 발표자료 (측정 전후 비교표, 한계·원인 분석) | 선행: INFRA-08 | 담당: 신지호
- [ ] DOC-08 최종 보고서 | 선행: INFRA-08 | 담당: 공동
- [ ] DOC-09 시연 리허설 (현장 조명·소음 조건) | 선행: DOC-06 | 담당: 공동

---

## 상시 작업

- [ ] DOC-10 주간보고 작성 (금주 수행 결과 · 문제점 · 해결 방법 · 다음 예정작업) — 매주 반복 | 담당: 신지호 (각자 자기 작업물 내용 제공)
- [ ] INFRA-09 정기 통합: 각자 작업을 main에 합치고 Skeleton이 여전히 동작하는지 확인 — 주 1회 반복 | 담당: 공동 (이현종 주관)

## 리스크 & 대체 계획

| 리스크 | 조기 신호 | 대체 계획 |
|---|---|---|
| RKLLM 변환·실행 실패 / 모델 미지원 | BOARD-05, LLM-08 실패 | 지원 목록의 다른 모델 → CPU llama.cpp → 규칙 파서 + 소형 분류기 |
| 한국어 STT 소음 취약 | STT-07 mixed CER 급등 | 명령 어휘 제한, 마이크 게인·VAD 조정, ASK_CLARIFY로 재확인 |
| NPU 동시 구동 경합 | BOARD-08에서 tok/s 급락 | YOLO fps 하향, 발화 처리 중 YOLO 일시정지 |
| 발열 스로틀링 | BOARD-09 성능 저하 | 방열판·팬 강화, 부하 분산 |
| 보드 도착/고장 지연 | BOARD-01 | Mac·Colab에서 ONNX/CPU로 개발 지속 |
| 통합 막판 실패 | Gate 2 지연 | Phase 2를 최우선, 정기 통합(INFRA-09) |
| 시연 당일 실패 | — | DOC-06 영상 백업 |
