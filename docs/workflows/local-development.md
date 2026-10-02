# Local Development

## 어디서 무엇을 하나

| 작업 | Mac (M1, arm64) | Colab (x86 + GPU) | Orange Pi 보드 |
|---|---|---|---|
| 서비스 로직 개발 (가짜 메시지 입력) | ✅ | | ✅ |
| sherpa-onnx STT 실험, CER 측정 | ✅ | ✅ | ✅ (공식 수치) |
| YOLO 기본 모델 실행, 라벨링 | ✅ | | |
| YOLO 학습 | 느림 | ✅ 권장 | |
| ONNX → RKNN 변환 | ❌/비권장 | ✅ | ✅ (aarch64 휠, 확인 필요) |
| LLM LoRA 학습 | ❌ | ✅ | |
| HF → `.rkllm` 변환 | ❌ (x86 Linux 전용으로 알려짐, 확인 필요) | ✅ | ❌ |
| 최종 성능 측정 | | | ✅ **모든 공식 수치는 보드 기준** |

## 처음 clone 후

```bash
git clone https://github.com/samsung-team-jarvis/jarvis.git
cd jarvis
python3 -m venv .venv && source .venv/bin/activate
pip install pre-commit ruff
pre-commit install          # 커밋 전 자동 검사 (큰 파일·모델 파일 차단, ruff)
```

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
