"""LoRA 학습 → 베이스에 병합 → fp16 HF 모델로 저장 (LLM-07).

.venv-llm/bin/python -m training.llm.train_lora                         # Qwen3-0.6B, 데이터 v2
.venv-llm/bin/python -m training.llm.train_lora --limit 32 --epochs 1   # 끝까지 도는지만 확인
.venv-llm/bin/python -m bench.llm_eval --engine hf --finetuned --model runs/llm/<이름> --split val

- 입력은 services/llm_svc/prompt.py의 짧은 지시문 + 사용자 메시지, 정답은 함수 토큰 + 끝 토큰.
  정답 부분에만 loss를 건다 (지시문·사용자 메시지는 맞히게 하지 않는다).
- train으로 학습하고, epoch마다 val loss를 잰다. test는 쓰지 않는다 (비교는 bench/llm_eval.py로).
- 저장물(runs/llm/<이름>/): 병합된 fp16 모델, 토크나이저, train_log.json(설정·loss·입력 예시).
  git에 넣지 않는다 (docs/artifacts.md 등록부에 한 줄).
- 장치: CUDA면 bf16(지원하지 않는 GPU는 fp32), Mac(MPS)·CPU면 fp32로 학습한다.
  Mac(16GB)에서는 Qwen3-0.6B만 확인했다. 더 큰 모델은 training/colab/train_lora.ipynb.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import random
import subprocess
import sys
import time

from common.function_call import to_tokens
from services.llm_svc.prompt import FINETUNED_SYSTEM_PROMPT, user_message

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data/llm"
RUNS = ROOT / "runs/llm"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def load(path: pathlib.Path, limit: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in path.open(encoding="utf-8")]
    return rows[:limit]


def render_prompt(tok, record: dict) -> str:
    """chat template을 적용한 입력 문자열 (생성 시작 표시까지). 평가·보드도 같은 문자열을 쓴다."""
    messages = [
        {"role": "system", "content": FINETUNED_SYSTEM_PROMPT},
        {"role": "user", "content": user_message(record["instruction"], record["context"])},
    ]
    kwargs = {"add_generation_prompt": True, "tokenize": False}
    try:
        return tok.apply_chat_template(messages, enable_thinking=False, **kwargs)
    except TypeError:  # thinking 설정이 없는 모델
        return tok.apply_chat_template(messages, **kwargs)


def encode(tok, record: dict) -> tuple[list[int], list[int]]:
    """(입력 id, 정답 id). 정답은 함수 토큰 + 끝 토큰이고 나머지 자리는 -100(loss 제외)."""
    prompt_ids = tok(render_prompt(tok, record), add_special_tokens=False)["input_ids"]
    target_ids = tok(to_tokens(record["output"]) + tok.eos_token, add_special_tokens=False)[
        "input_ids"
    ]
    return prompt_ids + target_ids, [-100] * len(prompt_ids) + target_ids


def batches(items: list, size: int, pad_id: int, device: str):
    import torch

    for i in range(0, len(items), size):
        chunk = items[i : i + size]
        n = max(len(ids) for ids, _ in chunk)
        ids = torch.full((len(chunk), n), pad_id)
        labels = torch.full((len(chunk), n), -100)
        mask = torch.zeros((len(chunk), n), dtype=torch.long)
        for k, (x, y) in enumerate(chunk):
            ids[k, : len(x)] = torch.tensor(x)
            labels[k, : len(y)] = torch.tensor(y)
            mask[k, : len(x)] = 1
        yield ids.to(device), mask.to(device), labels.to(device)


def lr_lambda(warmup: int, total: int):
    """warmup 동안 선형으로 올리고, 그 뒤 cosine으로 0까지 내린다."""

    def f(step: int) -> float:
        if step < warmup:
            return (step + 1) / warmup
        return 0.5 * (1 + math.cos(math.pi * (step - warmup) / max(1, total - warmup)))

    return f


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        )
        return out.stdout.strip()
    except OSError:
        return ""


def load_model(model_id: str, dtype):
    from transformers import AutoModelForCausalLM

    try:
        return AutoModelForCausalLM.from_pretrained(model_id, dtype=dtype)
    except (ValueError, KeyError):  # Qwen3.5처럼 멀티모달 구조 (bench/llm_eval.py와 같은 처리)
        from transformers import AutoModelForImageTextToText

        return AutoModelForImageTextToText.from_pretrained(model_id, dtype=dtype)


def main() -> int:
    parser = argparse.ArgumentParser(description="LoRA 학습 후 병합해 fp16으로 저장한다")
    parser.add_argument("--model", default="Qwen/Qwen3-0.6B", help="베이스 (Instruct) 모델")
    parser.add_argument("--data", default="v2", help="데이터 버전 (data/llm/split_<버전>)")
    parser.add_argument("--name", default=None, help="저장 폴더 이름 (기본: llm_<모델>_jarvis_v1)")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch", type=int, default=4, help="한 번에 넣는 문장 수")
    parser.add_argument(
        "--accum", type=int, default=4, help="이만큼 모아서 한 번 갱신 (실제 배치=곱)"
    )
    parser.add_argument("--r", type=int, default=16, help="LoRA 차원")
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--dropout", type=float, default=0.05)
    parser.add_argument("--warmup", type=float, default=0.05, help="전체 갱신 횟수 중 warmup 비율")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None, help="앞에서 N개만 (빠른 확인용)")
    args = parser.parse_args()

    import torch  # 학습 환경(.venv-llm)에만 있다. 위의 함수들은 torch 없이 테스트한다
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        # bf16을 못 쓰는 GPU(Colab T4)는 fp32
        device = "cuda"
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32
    elif torch.backends.mps.is_available():
        device, dtype = "mps", torch.float32  # MPS fp16 학습은 loss가 불안정할 수 있어 fp32
    else:
        device, dtype = "cpu", torch.float32

    split_dir = DATA_DIR / f"split_{args.data}"
    name = args.name or f"llm_{args.model.split('/')[-1].lower()}_jarvis_v1"
    out = RUNS / name

    tok = AutoTokenizer.from_pretrained(args.model)
    model = load_model(args.model, dtype).to(device)
    model.config.use_cache = False
    lora = LoraConfig(
        r=args.r,
        lora_alpha=args.alpha,
        lora_dropout=args.dropout,
        target_modules=TARGET_MODULES,
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)

    train_records = load(split_dir / "train.jsonl", args.limit)
    train_items = [encode(tok, r) for r in train_records]
    val_items = [encode(tok, r) for r in load(split_dir / "val.jsonl", args.limit)]
    lengths = [len(x) for x, _ in train_items]
    print(
        f"device={device} dtype={dtype} eos={tok.eos_token!r} trainable={trainable:,} "
        f"train={len(train_items)} val={len(val_items)} "
        f"tokens mean={sum(lengths) / len(lengths):.0f} max={max(lengths)}",
        flush=True,
    )

    params = [p for p in model.parameters() if p.requires_grad]
    total_steps = math.ceil(len(train_items) / (args.batch * args.accum)) * args.epochs
    warmup = max(1, int(total_steps * args.warmup))
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda(warmup, total_steps))
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id

    log = {
        "base": args.model,
        "data": f"split_{args.data}",
        "commit": git_commit(),
        "device": device,
        "dtype": str(dtype),
        "system_prompt": FINETUNED_SYSTEM_PROMPT,
        "prompt_example": render_prompt(tok, train_records[0]),
        "target_example": to_tokens(train_records[0]["output"]) + tok.eos_token,
        "eos_token": tok.eos_token,
        "eos_token_id": tok.eos_token_id,
        "lora": {
            "r": args.r,
            "alpha": args.alpha,
            "dropout": args.dropout,
            "targets": TARGET_MODULES,
        },
        "lr": args.lr,
        "batch": args.batch * args.accum,
        "epochs": args.epochs,
        "warmup_steps": warmup,
        "total_steps": total_steps,
        "seed": args.seed,
        "train_n": len(train_items),
        "val_n": len(val_items),
        "tokens_mean": sum(lengths) / len(lengths),
        "tokens_max": max(lengths),
        "trainable_params": trainable,
        "history": [],
    }
    start, step = time.monotonic(), 0
    for epoch in range(args.epochs):
        model.train()
        random.shuffle(train_items)
        running, count = 0.0, 0
        for i, (ids, mask, labels) in enumerate(batches(train_items, args.batch, pad, device)):
            loss = model(input_ids=ids, attention_mask=mask, labels=labels).loss
            (loss / args.accum).backward()
            running, count = running + loss.item(), count + 1
            if (i + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(params, 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
                step += 1
                if device == "mps":
                    torch.mps.empty_cache()  # 16GB Mac에서 메모리가 쌓여 스왑으로 멈추지 않게
                if step % 10 == 0:
                    print(
                        f"epoch {epoch + 1} step {step}/{total_steps} "
                        f"loss {running / count:.4f} {time.monotonic() - start:.0f}s",
                        flush=True,
                    )
        model.eval()
        with torch.no_grad():
            val = [
                model(input_ids=a, attention_mask=m, labels=y).loss.item()
                for a, m, y in batches(val_items, args.batch, pad, device)
            ]
        entry = {
            "epoch": epoch + 1,
            "train_loss": running / count,
            "val_loss": sum(val) / len(val),
            "seconds": round(time.monotonic() - start),
        }
        log["history"].append(entry)
        print(entry, flush=True)

    merged = model.merge_and_unload()
    merged.config.use_cache = True
    out.mkdir(parents=True, exist_ok=True)
    merged.to(torch.float16).save_pretrained(out)
    tok.save_pretrained(out)
    (out / "train_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
