from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a small knowledge-guided ICU transformer.")
    parser.add_argument("--pseudo-labels", default="backend/scripts/knowledge_guided_pretrain/out/pseudo_labels.jsonl")
    parser.add_argument("--kg-samples", default="backend/scripts/knowledge_guided_pretrain/out/kg_samples.jsonl")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        import torch  # type: ignore  # noqa: F401
        import transformers  # type: ignore  # noqa: F401
    except Exception:
        print("torch/transformers are required only in the offline pretraining environment: pip install torch transformers datasets")
        return 2
    print(f"knowledge-guided pretrain entry ready: pseudo={args.pseudo_labels}, kg={args.kg_samples}, output={args.output_dir}, dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
