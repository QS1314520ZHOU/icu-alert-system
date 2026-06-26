from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.alert_engine.features.mdro_features import MDRO_FEATURE_SCHEMA_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description="Create MDRO control analysis summary placeholder.")
    parser.add_argument("--output-dir", default="docker/icu-models/mdro-control")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "topic": "mdro_control",
        "feature_schema_version": MDRO_FEATURE_SCHEMA_VERSION,
        "validation_status": "internal_only",
        "analyses": {
            "retrospective_cohort": {"n": None},
            "transmission_network": {"nodes": None, "edges": None},
            "cost_effectiveness": {"triggered_screening_cost": None, "universal_screening_cost": None},
        },
        "wgs": {"available": False, "reason": "requires external microbiology WGS data; not implemented in this phase"},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out / "summary.json"))


if __name__ == "__main__":
    main()
