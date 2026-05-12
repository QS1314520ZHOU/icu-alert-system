from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate structured KG samples for knowledge-guided pretraining.")
    parser.add_argument("--output", default="backend/scripts/knowledge_guided_pretrain/out/kg_samples.jsonl")
    args = parser.parse_args()
    rows = [
        {
            "finding_key": "lactate_rise",
            "evidence": ["sepsis_signal", "map_low", "lactate_high"],
            "target": "septic_shock",
            "source": "clinical_knowledge_graph_builtin",
        }
    ]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} KG sample(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
