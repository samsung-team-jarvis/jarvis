# Local Development

## 어디서 무엇을 하나

| 작업 | Mac (M1, arm64) | Colab (x86 + GPU) | Orange Pi 보드 |
|---|---|---|---|
| 서비스 로직 개발 (가짜 메시지 입력) | ✅ | | ✅ |
| sherpa-onnx STT 실험, CER 측정 | ✅ | ✅ | ✅ (공식 수치) |
| YOLO 기본 모델 실행, 라벨링 | ✅ | | |
| YOLO 학습 | 느림 | ✅ 권장 | |
| ONNX → RKNN 변환 | ❌ (macOS 휠 없음. Docker amd64로는 가능) | ✅ 기본 | △ aarch64 휠은 있으나 의존성 onnxoptimizer 소스 빌드 필요 |
| LLM LoRA 학습 | ❌ | ✅ | |
| Ultralytics 공식 RKNN export (방법 B) | ❌ | ✅ | ❌ (x86 Linux 전용) |
| HF → `.rkllm` 변환 | ❌ | ✅ | ❌ (rkllm-toolkit은 Linux x86_64 · Python 3.10~3.12 전용) |
| 최종 성능 측정 | | | ✅ **모든 공식 수치는 보드 기준** |

근거와 절차: [yolo-to-rknn](../../recipes/yolo-to-rknn.md), [llm-to-rkllm](../../recipes/llm-to-rkllm.md) (2026-10-02 공식 저장소 확인). 변환은 **Colab 노트북이 기본 경로**다 ([training](../../training/README.md)). Mac에서 RKNN 변환을 확인하려면 `bash training/convert/docker_rknn_smoke.sh` (Docker, x86 에뮬레이션이라 느림).

## 처음 clone 후

```bash
git clone https://github.com/samsung-team-jarvis/jarvis.git
cd jarvis
python3 scripts/setup.py          # Windows: py scripts\setup.py
source .venv/bin/activate         # 작업할 때마다 (Windows: .venv\Scripts\activate)
```

`setup.py`는 `.venv` 생성 → `requirements-dev.txt` 설치(pre-commit·ruff·pytest, CI와 같은 버전) → git 훅 설치 → 빠른 검사를 한다. 여러 번 실행해도 안전하다.
합류 절차 전체는 [온보딩 체크리스트](../onboarding.md).

설치되는 검사:
- 커밋 전: 큰 파일·모델 가중치·원본 데이터 차단, ruff, 문서 링크
- 커밋 메시지: `prefix(scope): #N summary` 형식 ([Git Convention](../conventions/git.md))
- push 전: 브랜치 이름 형식, main 직접 push 차단

Claude Code로 이 repo를 열었을 때 훅이 설치되어 있지 않으면 세션 시작 시 경고가 뜬다 (`.claude/settings.json`).

의존성 파일(`requirements*.txt` / `pyproject.toml`)이 생기면 이 절에 설치 명령을 추가한다.

## 보드 접속

보드 세팅 절차는 [recipes/board-setup.md](../../recipes/board-setup.md). 접속 정보(IP, 계정)는 repo에 커밋하지 않고 팀 메신저·개인 `~/.ssh/config`에 둔다.

## 문서만 바꿨을 때 최소 검증

```bash
git diff --check
pre-commit run --all-files
```

## 큰 파일

- 모델 가중치·원본 데이터는 git에 넣지 않는다 (`.gitignore`, pre-commit `check-added-large-files`).
- 공유는 팀 Google Drive. 경로와 버전은 `data/` 또는 `training/`의 매니페스트 파일에 기록한다.
