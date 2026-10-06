# JARVIS — 스마트 자영업 서비스 어시스턴스: 자비스

혼자 가게를 운영하는 자영업자가 **"자비스, 후드 켜줘"** 한마디로 주방과 매장의 장치를 제어하고, 과열·방치 같은 위험을 먼저 알아채는 온디바이스 음성 비서.
음성·화면 인식·온도를 Orange Pi 5 Plus(RK3588 NPU)에서 **인터넷 없이** 처리하고, 결정론적 Safety Guard를 거쳐 **가상 주방(메타버스)** 의 장치를 움직인다. 실물 제어 하드웨어는 쓰지 않는다 ([결정](docs/decisions/2026-10-05-virtual-kitchen-demo.md)).

2026-2 모바일시스템응용프로젝트 · 삼성팀 · 산업체 멘토 마음AI

## 어떻게 동작하나

```text
 🎤 "자비스, 후드 켜줘"
   │
   ▼
 audio_svc ── VAD → STT(SenseVoice) → 호출어 ──▶ stt/text
                                                   │
 llm_svc ──── STT 오인식 사전 → 규칙 파서 (→ LLM) ──▶ llm/function_call  {"action":"TURN_ON","target":"hood"}
                                                   │
 🖥 가상 주방 ─캡처 화면→ vision_svc · ─온도→ kitchen_gw ─▶ fusion_svc ─▶ safety_guard ──▶ control/command ─▶ kitchen_gw ─▶ 가상 주방 장치
                                                   │
 audio_svc(TTS) ◀── guard/decision ── "후드를 켰습니다"
```

- 서비스는 프로세스마다 따로 돌고, **로컬 MQTT**로 [정해진 형식](docs/architecture/interfaces.md)의 메시지만 주고받는다.
- **안전은 LLM에 맡기지 않는다**: LLM은 명령을 해석만 하고, 위험 판단은 규칙 기반 Safety Guard, 마지막 차단은 가상 주방 쪽 자체 안전장치가 한다 ([안전 3계층](docs/decisions/2026-10-01-safety-layers.md)).
- 지금 동작하는 장치는 3종(후드, 1·2번 화구)이다. 8종(튀김기·조명·에어컨·선풍기·음악·결제 추가)으로 넓히는 중이다 (PLAN LLM-13·14).
- 진행 상황은 [PLAN](docs/PLAN.md)의 Phase·Gate가 기준이다.

## 구성 요소

| 구성 | 하는 일 | 담당 (작업물) | 문서 |
|---|---|---|---|
| `services/audio_svc` | 마이크 → VAD → STT → 호출어, 음성 응답(TTS) | 이현종 ② | [README](services/audio_svc/README.md) |
| `services/llm_svc` | 받아쓴 문장 → 명령 (규칙 파서, LLM 연결 예정) | 이현종 ② | [README](services/llm_svc/README.md) |
| `services/safety_guard` · `fusion_svc` | 상황 인식(State Machine), 위험 판단·차단 | 최지환 ③ | (예정) |
| `services/kitchen_gw` | 보드 ↔ 가상 주방 연결(제어·결과 확인·온도·생존 신호), 가짜 가상 주방 | 이현종 ② | [README](services/kitchen_gw/README.md) |
| 가상 주방 (Unity) | 장면·장치·가상 온도·캡처 화면 | 최석진 ④ | (예정 — [결정](docs/decisions/2026-10-05-unity-virtual-kitchen.md), [연결 안내](recipes/unity-kitchen-link.md)) |
| `services/vision_svc` · `training/yolo` | YOLOv8 RKNN 객체 인식, 데이터·학습 | 신지호 ① · 이현종 | [training](training/README.md) |
| `services/recorder` · `simulator` | 모든 메시지 녹화 / 가상 주방 없이 가짜 메시지 재생 | 이현종 ② | [recorder](services/recorder/README.md) · [simulator](services/simulator/README.md) |
| `training/llm` | LLM 데이터(기획 시트 → Seed·Paraphrase·분할) | 이현종 ② | [README](training/llm/README.md) |
| `bench` | 지연 분해, STT·LLM 평가, 녹음 도구 | 이현종 ② | [README](bench/README.md) |

## 빠른 시작

```bash
git clone https://github.com/samsung-team-jarvis/jarvis.git && cd jarvis
python3 scripts/setup.py          # 가상환경 · 의존성 · git 훅 · 검사까지 한 번에
```

음성 모델(SenseVoice·Silero VAD·한국어 VITS)은 git에 없다 → [모델 받기](services/audio_svc/README.md#모델-받기-한-번만).

```bash
# 서비스 한 번에 띄우기 (MQTT 브로커 필요 — docs/workflows/local-development.md)
python3 scripts/launch.py                                    # recorder → kitchen_gw → llm_svc → audio_svc(마이크)
python3 scripts/launch.py --arg audio_svc="--input data/stt/cmds.wav --realtime --session demo" --until audio_svc
python -m bench.latency data/sessions/demo.jsonl             # 발화 끝 → 명령 구간별 지연

# 하드웨어 없이
python -m services.simulator services/simulator/scenarios/overheat.yaml --speed 10
python -m services.llm_svc parse "3분 뒤에 2번 불 꺼"         # 문장 하나 → 명령
```

처음 합류했다면 [온보딩 체크리스트](docs/onboarding.md)부터. 환경 상세는 [Local Development](docs/workflows/local-development.md).

## 폴더 구조

```text
common/      메시지 봉투·MQTT 버스·명령 스키마 (모든 서비스 공용)
services/    서비스 (프로세스 하나 = 폴더 하나)
bench/       측정 스크립트 (지연·STT·LLM 평가, 녹음 도구)
training/    학습·변환 (YOLO·LLM 데이터, RKNN/RKLLM 변환, Colab 노트북)
data/        매니페스트·대본·LLM 텍스트 데이터 (녹음·사진·모델 파일은 git 제외)
docs/        계획·아키텍처·지표·결정 기록·규칙
recipes/     따라 하는 절차 (보드 세팅, 변환, STT 평가·녹음, 서비스 추가)
scripts/     개발 도구 (setup, 런처, 컨벤션 검사)
```

## 작업 방식

모든 작업은 **이슈 → 브랜치 → PR → 머지**. 브랜치·커밋·PR 형식은 훅과 CI가 검사한다 → [Git Convention](docs/conventions/git.md).
측정값은 **실측만** [METRICS](docs/METRICS.md)에 남기고, 최종 판정은 보드 기준이다.

## 문서

[문서 인덱스](docs/index.md) · [PLAN](docs/PLAN.md) · [아키텍처](docs/architecture/overview.md) · [인터페이스 규격](docs/architecture/interfaces.md) · [METRICS](docs/METRICS.md) · [결정 기록](docs/decisions/index.md) · [Agent Guide](AGENTS.md)
