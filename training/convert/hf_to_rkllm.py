"""Hugging Face LLM → RKLLM 변환 (RK3588).

실행 환경: Linux x86_64 + Python 3.10~3.12 + rkllm-toolkit (Colab). macOS·보드에서는 불가.
인자 이름은 rknn-llm 공식 예제(examples/rkllm_api_demo/export/export_rkllm.py) 기준.
절차 설명: recipes/llm-to-rkllm.md

사용:
    python training/convert/hf_to_rkllm.py --model ./merged_fp16 --dataset quant.json \
        --out jarvis_w8a8.rkllm

quant.json: [{"input": "...", "target": "..."}, ...] (Train 발화에서만, chat template 적용한 input)
샘플 변환 확인에는 rknn-llm 예제의 data_quant.json을 쓴다 (training/colab/convert_rkllm.ipynb).
대소문자 등 인자 값은 공식 예제 그대로 쓴다 (RK3588, W8A8).
"""

import argparse
import pathlib
import sys
import time

RK3588_DTYPES = ["W8A8", "W8A8_G128", "W8A8_G256", "W8A8_G512"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", required=True, help="HF 모델 디렉터리 또는 허브 이름")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--lora", default=None, help="LoRA 어댑터 경로 (분리 변환 시)")
    parser.add_argument("--dataset", required=True, type=pathlib.Path, help="캘리브레이션 JSON")
    parser.add_argument("--quant", choices=RK3588_DTYPES, default="W8A8")
    parser.add_argument(
        "--load-dtype", choices=["float32", "float16", "bfloat16"], default="float32"
    )
    parser.add_argument("--npu-cores", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--max-context", type=int, default=4096)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dataset.exists():
        print(f"캘리브레이션 파일이 없습니다: {args.dataset}")
        return 1
    if args.max_context % 32 or not 0 < args.max_context <= 16384:
        print("--max-context는 32의 배수이고 16384 이하여야 합니다.")
        return 1

    from rkllm.api import RKLLM  # rkllm-toolkit이 설치된 Linux x86_64에서만 import 가능

    llm = RKLLM()
    started = time.monotonic()
    steps = [
        (
            "load_huggingface",
            lambda: llm.load_huggingface(
                model=args.model,
                model_lora=args.lora,
                device=args.device,
                dtype=args.load_dtype,
            ),
        ),
        (
            "build",
            lambda: llm.build(
                do_quantization=True,
                optimization_level=1,
                quantized_dtype=args.quant,
                quantized_algorithm="normal",
                target_platform="RK3588",
                num_npu_core=args.npu_cores,
                dataset=str(args.dataset),
                hybrid_rate=0,
                max_context=args.max_context,
            ),
        ),
        ("export_rkllm", lambda: llm.export_rkllm(str(args.out))),
    ]
    for name, call in steps:
        if call() != 0:
            print(f"{name} 실패")
            return 1
        print(f"{name} 완료")

    size_mb = args.out.stat().st_size / 1e6
    print(f"OK: {args.out} ({size_mb:.1f} MB, {args.quant}, {time.monotonic() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
