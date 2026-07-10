from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Train local ICU LoRA adapter from deidentified SFT JSONL.")
    parser.add_argument("--data", default="backend/scripts/lora_finetune/out/sft.jsonl")
    parser.add_argument("--base-model", required=False, default="")
    parser.add_argument("--output-dir", default="backend/scripts/lora_finetune/out/adapter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        import transformers  # type: ignore  # noqa: F401
        import peft  # type: ignore  # noqa: F401
    except Exception:
        print("transformers/peft are required only in the offline training environment: pip install transformers peft accelerate datasets")
        return 2
    print(f"LoRA training entry ready: data={args.data}, base_model={args.base_model}, output={args.output_dir}, dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
