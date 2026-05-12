from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate local ICU LoRA adapter on held-out deidentified samples.")
    parser.add_argument("--predictions", default="")
    parser.add_argument("--output", default="backend/scripts/lora_finetune/out/eval.json")
    args = parser.parse_args()
    result = {"available": bool(args.predictions), "metrics": {}, "note": "wire clinical rubric / expert review here before production"}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote evaluation stub to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
