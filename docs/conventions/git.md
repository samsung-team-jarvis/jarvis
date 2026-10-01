# Git Convention

## 작업 흐름 (모든 작업 공통)

```text
1. GitHub 이슈 생성   →  제목: [PLAN-ID] 작업 요약   (예: [STT-01] SenseVoice 한국어 첫 받아쓰기)
2. 브랜치 생성        →  prefix/{scope}/{이슈번호}-work-summary
3. 작업 · 커밋         →  prefix(scope): #{이슈번호} work summary
4. push · PR 생성     →  [PREFIX](scope): #{이슈번호} work summary,  본문에 Closes #{이슈번호}
5. 리뷰 승인 1명 → 머지 →  이슈 자동 종료, 브랜치 자동 삭제
6. docs/PLAN.md 체크   →  같은 PR 안에서 해당 항목 [x] + 근거(PR 번호)
```

- `main`에 직접 push 금지 (브랜치 보호). 모든 변경은 PR로.
- PLAN에 없는 작업이면 이슈를 만들기 전에 PLAN에 항목부터 추가한다.
- 이슈 하나 = PR 하나가 기본. 이슈가 크면 sub-issue로 쪼갠다.

## Branch

```text
prefix/{scope}/{이슈번호}-work-summary
```

```text
chore/root/1-harness-setup
feat/audio/12-sensevoice-hello
feat/vision/20-yolo-rknn-int8
exp/llm/31-qwen-baseline
fix/ble/40-ack-retry-timeout
docs/docs/8-interfaces-v0-2
```

`work-summary`는 영어 kebab-case.

## Commit

```text
prefix(scope): #{이슈번호} work summary

body (선택: 왜 바꿨는지, 측정 결과, 남은 문제)
```

```text
chore(root): #1 AGENTS/CLAUDE 허브 추가
feat(audio): #12 sherpa-onnx SenseVoice 받아쓰기 스크립트 추가
exp(llm): #31 Qwen2.5-0.5B 프롬프트 Baseline 측정 결과 기록
fix(ble): #40 ACK 타임아웃 시 재시도 누락 수정
```

## Commit Splitting

커밋 수를 1~2개로 제한하지 않는다. 독립적으로 리뷰·revert·검증 가능한 단위로 나눈다.
아래 중 하나라도 다르면 별도 커밋을 우선 고려한다.

- 변경 surface가 다름: 서비스 코드 / 공통 모듈 / 학습·변환 스크립트 / 펌웨어 / 측정 결과 / 문서 / 설정·CI
- 검증 방법이 다름 (Mac에서 확인 / 보드에서 확인 / ESP32에서 확인)
- 순수 refactor·rename·remove와 동작 변경이 섞임
- 측정 결과 기록(`exp`)과 그 측정을 만든 코드 변경

절차는 [commit-planning-workflow](../../.claude/skills/commit-planning-workflow/SKILL.md).

## Scope

| Scope | Use when |
|---|---|
| `root` | 루트 설정, AGENTS/CLAUDE, pre-commit, coderabbit |
| `docs` | `docs/*` |
| `recipes` | `recipes/*` |
| `templates` | `templates/*` |
| `skills` | `.claude/skills/*` |
| `github` | `.github/*` |
| `common` | `common/*` 메시지 스키마·버스·로거 |
| `audio` | `services/audio_svc` (VAD·STT·호출어) |
| `vision` | `services/vision_svc` |
| `llm` | `services/llm_svc` |
| `fusion` | `services/fusion_svc` (State Machine) |
| `guard` | `services/safety_guard`, 규칙 파서 |
| `ble` | `services/ble_gw` |
| `recorder` | `services/recorder` |
| `firmware` | `firmware/esp32` |
| `training` | `training/*` (YOLO·LLM 학습, Colab 노트북, 변환 스크립트) |
| `bench` | `bench/*` 측정 스크립트 |
| `data` | `data/*` 매니페스트·split 파일 |

여러 surface가 함께 바뀌면 가장 중요한 범위를 scope로 잡고 나머지는 body에 적는다. 무관한 변경이면 커밋을 나눈다.

## Prefix

| Prefix | Description |
|---|---|
| `feat` | 새로운 기능 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변경 없는 구조 개선 |
| `exp` | 실험·측정 실행과 결과 기록 (METRICS 갱신) |
| `test` | 테스트·fixture·검증 코드 |
| `docs` | 문서 |
| `chore` | 설정, 의존성, CI, 기타 |
| `style` | 동작 변경 없는 formatting |
| `rename` | 파일·폴더 이름 변경 또는 이동 |
| `remove` | 파일 삭제만 |

## PR

- 제목: `[PREFIX](scope): #{이슈번호} work summary` — PREFIX는 대문자
  - 예: `[FEAT](audio): #12 SenseVoice 받아쓰기 스크립트 추가`
- 본문: [PR 템플릿](../../.github/pull_request_template.md)과 [Pull Request Writing](../workflows/pull-request-writing.md) 기준. `Closes #{이슈번호}` 필수.
- 실제 실행한 검증만 `Verification`에 적는다.
- 머지 방식: **Create a merge commit** (나눠 둔 커밋을 보존). 머지 후 브랜치는 자동 삭제된다.

## 금지

- 모델 가중치(`*.pt`, `*.onnx`, `*.rknn`, `*.rkllm` 등)와 원본 데이터(wav, jpg, mp4) 커밋
- `.env`, 토큰, 개인 설정 커밋
- 커밋 메시지에 Co-Authored-By 등 AI 도구 서명 푸터 추가
- `main` force push
