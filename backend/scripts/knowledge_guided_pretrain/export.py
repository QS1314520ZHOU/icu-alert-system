from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import AppConfig
from app.services.local_model_paths import local_model_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Export knowledge-guided foundation model metadata.")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    target = Path(args.output) if args.output else local_model_dir(AppConfig(), "knowledge_pretrain_dir", "knowledge-guided-pretrain") / "metadata.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"provider": "knowledge_guided", "embedding_dim": 768, "tasks": ["mortality", "aki", "circulation_failure"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote metadata to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
