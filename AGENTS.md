# JARVIS Agent Guide

agent용 허브 문서다. 상세 규칙을 여기에 복붙하지 말고, 작업 종류에 맞는 source of truth 문서를 먼저 읽는다.

## 저장소 정체

- Product: JARVIS — 혼자 가게를 운영하는 자영업자를 위한 온디바이스 상황 인식 어시스턴트 (등록명 "스마트 자영업 서비스 어시스턴스: 자비스", 2026-2 모바일시스템응용프로젝트, 삼성팀, 멘토 마음AI)
- 구조: 음성(실제 마이크)·가상 주방의 캡처 화면·온도 → Orange Pi(RK3588 NPU) 오프라인 추론 → State Machine + Safety Guard → 가상 주방(메타버스)의 장치. 실물 제어 하드웨어는 없다 ([decision](./docs/decisions/2026-10-05-virtual-kitchen-demo.md))
- 작업 키: GitHub 이슈 번호 `#N` (이슈 제목에 PLAN ID, 예: `[STT-01]`)
- 개발 PC는 M1 Mac — 일부 변환·학습은 Colab/보드에서만 가능 ([local-development](./docs/workflows/local-development.md))

## 기본 순서

1. `docs/PLAN.md`에서 작업 ID와 완료 기준 확인 (없으면 PLAN에 먼저 추가)
2. GitHub 이슈 생성 → 브랜치 생성
3. 필요하면 spec 작성 (`templates/`)
4. 구현 → 검증 (실행 장소 명시)
5. 문서 갱신 (PLAN / METRICS / interfaces / decisions)
6. 커밋 계획 → 커밋 → push → PR (`Closes #N`)
7. 리뷰 승인 → merge commit으로 머지

절차 상세: [task-workflow](./.claude/skills/task-workflow/SKILL.md), 형식: [Git Convention](./docs/conventions/git.md)

## 작업 유형별 라우팅

| 작업 유형 | 먼저 볼 문서 |
|---|---|
| 작업 시작 (PLAN ID) | `.claude/skills/task-workflow/SKILL.md`, `docs/PLAN.md` |
| 서비스 코드 추가·수정 | `docs/architecture/interfaces.md`, `docs/conventions/coding.md`, `recipes/add-service.md`, `templates/service.spec.md` |
| 구조·자원 배치 판단 | `docs/architecture/overview.md`, `docs/decisions/index.md` |
| 보드 세팅·버전 | `recipes/board-setup.md`, `docs/conventions/versions.md` |
| YOLO 학습·RKNN 변환 | `recipes/yolo-to-rknn.md`, `.claude/skills/experiment-workflow/SKILL.md` |
| LLM 데이터·학습·RKLLM 변환 | `recipes/llm-to-rkllm.md`, `docs/architecture/interfaces.md` §3, `.claude/skills/experiment-workflow/SKILL.md` |
| STT 평가 | `recipes/stt-eval.md`, `.claude/skills/experiment-workflow/SKILL.md` |
| 측정·실험 기록 | `docs/workflows/experiment.md`, `docs/METRICS.md`, `templates/experiment.spec.md` |
| 안전 규칙 (Guard·ESP32) | `docs/decisions/2026-10-01-safety-layers.md`, `docs/architecture/overview.md` §2 |
| 결정 기록 | `docs/decisions/index.md`, `docs/decisions/open-questions.md` |
| 커밋 분해 | `.claude/skills/commit-planning-workflow/SKILL.md`, `docs/conventions/git.md` |
| PR 작성 | `.claude/skills/pr-prep-workflow/SKILL.md`, `docs/workflows/pull-request-writing.md` |
| AI 도구 설정 (Codex·Gemini·Cursor 등) | `docs/agent/tools.md` |
| harness·문서 구조 변경 | `.claude/skills/verify-agent-docs/SKILL.md`, `docs/agent/index.md`, `docs/index.md` |

## 필수 작업 원칙

- **Walking Skeleton 우선**: 끝까지 연결된 단순 버전이 먼저, 고도화는 나중 ([decision](./docs/decisions/2026-10-01-walking-skeleton-first.md)).
- **인터페이스 먼저**: 모듈 간 데이터는 interfaces 문서에 정의된 형식만 쓴다. 바꾸려면 문서부터.
- **실측만 기록**: 추정 수치를 문서·PR에 쓰지 않는다. 미측정은 `측정 예정`. 최종 수치는 보드 기준.
- **안전 규칙 위반 금지**: LLM 출력은 Safety Guard를 거친다. 위험 감지는 LLM을 거치지 않는다. 가상 주방은 자체 안전장치(생존 신호 끊김·온도 상한 → 가열 장치 OFF)를 가진다. 실물 가스·220V·가열 장치는 다루지 않는다.
- **버전 고정**: 변환 툴·보드 런타임은 `docs/conventions/versions.md`의 버전만 쓴다.
- **확실하지 않은 기술 정보는 "(확인 필요)"** 로 표시하고 공식 저장소·문서로 확인한 뒤 지운다.
- 요청 범위 밖 기능·추상화·refactor를 추가하지 않는다.
- 커밋은 독립적으로 리뷰·revert·검증 가능한 단위로 나눈다.

## 검증

```bash
git diff --check
python3 scripts/check_doc_links.py              # 문서 변경 시
ruff check . && ruff format --check .           # Python 변경 시
python3 scripts/check_conventions.py branch     # 브랜치 이름
pre-commit run --all-files                      # 설치한 경우
```

브랜치·커밋·PR 형식은 로컬 훅과 CI가 검사한다 ([자동 검사](./docs/conventions/git.md)). 검사가 실패하면 우회(`--no-verify`, force push)하지 말고 형식을 고친다. 작업 시작 전 git 훅 설치 여부를 확인하고, 없으면 `python3 scripts/setup.py` 실행을 안내한다.

보드·가상 주방이 필요한 검증을 못 했으면 "미검증"으로 남기고 이유를 적는다.

## 완료 후 확인

- 이슈·PLAN의 완료 기준 충족
- PLAN / METRICS / interfaces / decisions 중 필요한 문서 갱신
- 임시 파일, dead code, 모델 가중치·원본 데이터가 diff에 없음
- 실행한 검증과 생략한 검증(이유 포함)을 요약에 남김

## 하지 말 것

- `AGENTS.md`·`CLAUDE.md`에 긴 규칙 원문, 진행 상황, 작업 로그를 넣지 않는다.
- `docs/*` 내용을 복붙해 중복 source of truth를 만들지 않는다.
- `main`에 직접 push하지 않는다.
- 커밋에 Co-Authored-By 등 AI 서명 푸터를, PR 본문에 "Generated with ..." 서명 줄을 넣지 않는다.
