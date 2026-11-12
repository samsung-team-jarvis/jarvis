#!/usr/bin/env bash
# 학습한 HF 모델 폴더(LoRA 병합 fp16) → GGUF (LLM-18, llama.cpp로 CPU 실행).
# 변환 스크립트는 llama-cpp-python에 든 llama.cpp와 같은 커밋을 쓴다 (버전: docs/conventions/versions.md).
# Mac·Linux 어디서나 된다 (x86 전용 도구 없음). torch·transformers가 있는 .venv-llm으로 실행한다.
# 사용: bash training/convert/hf_to_gguf.sh runs/llm/llm_qwen3-0.6b_jarvis_v4 q8_0   # f16 | bf16 | q8_0
# 결과: runs/llm/<모델 이름>-<형식>.gguf (git 제외 — 등록부 docs/artifacts.md에 기록)
set -euo pipefail

MODEL="${1:?모델 폴더 (저장소 안 경로)}"
TYPE="${2:-q8_0}"
LLAMA_CPP_COMMIT="${LLAMA_CPP_COMMIT:-0c1e57098bba43ac29e6e3b677cdceebdd22334f}"  # llama-cpp-python 0.3.36
REPO_ROOT="$(git rev-parse --show-toplevel)"
PY="${PYTHON:-$REPO_ROOT/.venv-llm/bin/python}"
SRC="${XDG_CACHE_HOME:-$HOME/.cache}/jarvis/llama.cpp"  # 저장소 밖 (pytest가 그 안의 테스트를 줍지 않게)
OUT="$REPO_ROOT/runs/llm/$(basename "$MODEL")-$TYPE.gguf"

# 변환 스크립트와 gguf 패키지만 필요하다 → 고정 커밋 하나만 받는다
if [ "$(git -C "$SRC" rev-parse HEAD 2>/dev/null)" != "$LLAMA_CPP_COMMIT" ]; then
  rm -rf "$SRC" && mkdir -p "$SRC"
  git -C "$SRC" init -q
  git -C "$SRC" fetch -q --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_CPP_COMMIT"
  git -C "$SRC" checkout -q FETCH_HEAD
fi
"$PY" -m pip install -q "$SRC/gguf-py"

"$PY" "$SRC/convert_hf_to_gguf.py" "$REPO_ROOT/$MODEL" --outtype "$TYPE" --outfile "$OUT"
ls -l "$OUT"
