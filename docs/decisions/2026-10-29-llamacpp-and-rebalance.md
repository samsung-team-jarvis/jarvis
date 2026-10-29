# Decision: LLM은 llama.cpp(CPU)로, 3명 기준 작업 재분배

## Status
- Accepted ([작업물 4개 분할](./2026-10-02-deliverables-split.md)·[작업 재분배](./2026-10-04-task-rebalance.md)를 보완 — 작업물 경계는 그대로, ①의 담당과 LLM 실행 경로가 바뀐다)

## Date
- 2026-10-29

## Context
- **RKLLM 변환을 쓸 수 없다.** 변환 툴킷(rkllm-toolkit)은 x86_64 Linux 전용이다. 기본 경로인 학교 서버 변환 도커는 접속 방법이 정해지지 않았고, Mac의 Docker(amd64 에뮬레이션)로 LoRA v4를 변환해 보니 4시간이 넘도록 첫 층 최적화가 끝나지 않았다 (#113). Colab 노트북(BOARD-06)은 담당자가 실행하지 못했다.
- **보드 지급 여부를 모른다.** 보드에서만 잴 수 있는 값(NPU 속도·RAM·전력)은 하나도 없다.
- **신지호가 프로젝트를 진행하지 않는다.** ① 비전 데이터·모델 + 보드 + 팀 운영의 남은 작업 21건(BOARD-01~06·09, STT-02, VIS-01~07·09, DOC-03·05·07·10)에 담당이 없다.
- PLAN 리스크표에 이미 "RKLLM 변환·실행 실패 → CPU llama.cpp" 대체 경로가 있다.

## Options
- Option A: RKLLM을 계속 기다린다 (학교 서버 · Colab). 보드도 와야 한다.
- Option B: **LLM을 llama.cpp(GGUF 8비트)로 CPU에서 돌린다.** NPU는 YOLO(RKNN)만.
- Option C: LLM을 빼고 규칙 파서만 쓴다.

## Decision
- 선택한 안: **B** (결정: 이현종, 2026-10-29)
  - GGUF 변환과 llama.cpp 실행은 Mac에서 바로 된다. **양자화 전후 정확도를 같은 test로 지금 잴 수 있다** (RKLLM은 보드가 있어야 했다).
  - 같은 GGUF 파일이 보드(ARM CPU)에서도 돈다. 보드가 오면 tok/s·RAM만 더 잰다. 끝내 없으면 노트북에서 같은 구성으로 오프라인 시연한다 — 인터넷 없이 기기 안에서 추론한다는 점은 같다.
  - LLM이 NPU를 쓰지 않으므로 YOLO와 NPU를 나눠 쓰는 문제가 없어진다. 대신 LLM과 STT가 CPU를 나눠 쓴다 (BOARD-08에서 측정).
  - A는 일정이 외부에 달려 있고, C는 학습한 모델(test 89.2%, 규칙 파서 82.5%)을 버린다.
- **작업 재분배** — 작업물 경계는 그대로, 일에 가까운 사람에게 넘긴다. 팀장은 따로 두지 않는다.

| 작업 | 이후 | 이유 |
|---|---|---|
| BOARD-05·06, LLM-08 (RKLLM) | 취소 → LLM-18 (GGUF · llama.cpp) | 위 결정 |
| BOARD-01~04·09, STT-02 (보드 세팅·확인) | 이현종 | 보드 recipe·런처를 만든 사람. 보드를 받으면 |
| VIS-01·02 (기본 추론, 클래스 정의) | 최지환 | 클래스가 상황 인식(방치 판단)의 근거 |
| VIS-03·04·09 (가상 주방 화면 캡처 · 라벨) | 최석진 | Unity 장면 담당. 물체 위치를 알므로 상자 라벨을 Unity에서 내보내는 방법도 검토 |
| VIS-05~07 (학습 · 평가 · RKNN 변환) | 이현종 | 학습 노트북(VIS-10)·변환 스크립트를 만든 사람 |
| DOC-03 (멘토 질문) | 이현종 | |
| DOC-05·07 (기능 동결, 최종 발표) | 공동 | 팀장을 두지 않음 |
| DOC-10 (주간보고) | 돌아가며 | 각자 자기 작업 내용 제공은 그대로 |

## Consequences
- 이현종의 작업이 가장 많다 (LLM · STT · 보드 · YOLO 학습). 보드가 오지 않으면 보드 작업 6건이 빠진다. 밀리면 VIS-05~07을 최지환에게 넘기는 것을 먼저 검토한다.
- 잃는 것: NPU 가속. 보드 CPU에서 명령 한 건이 얼마나 걸리는지는 측정 전이다. 명령 출력은 15~19토큰이라 짧다.
- 학교 특강의 RKLLM 절차([llm-to-rkllm](../../recipes/llm-to-rkllm.md))와 변환 스크립트(`training/convert/hf_to_rkllm.py`)는 기록으로 남긴다.
- 영향: [PLAN](../PLAN.md) 작업물 표·담당·LLM-08/18, [overview](../architecture/overview.md) §1·§6, [versions](../conventions/versions.md)

## Revisit When
- 학교 서버 변환 도커를 쓸 수 있고 보드가 와서, NPU(RKLLM)와 CPU(llama.cpp)의 속도 차이를 같은 모델로 비교할 수 있을 때
- llama.cpp가 보드 CPU에서 명령 한 건을 시연에 쓸 수 없을 만큼 느릴 때
