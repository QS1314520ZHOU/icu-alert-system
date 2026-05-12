from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Export merged LoRA model provider config for vLLM/OpenAI-compatible runtime.")
    parser.add_argument("--model-id", default="local-icu-lora-medical")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--output", default="backend/scripts/lora_finetune/out/provider.json")
    args = parser.parse_args()
    provider = {
        "id": args.model_id,
        "name": "本院ICU LoRA医疗模型",
        "base_url": args.base_url,
        "api_key": "",
        "model": args.model_id,
        "purpose": "medical",
        "priority": 5,
        "enabled": False,
        "timeout": 60,
        "temperature": 0.1,
        "max_tokens": 2048,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(provider, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote provider config to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
