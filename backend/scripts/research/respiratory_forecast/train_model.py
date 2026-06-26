from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.alert_engine.features.respiratory_features import RESPIRATORY_FEATURE_SCHEMA_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description="Create respiratory forecast training metadata placeholder.")
    parser.add_argument("--output-dir", default="docker/icu-models/respiratory-forecast")
    args = parser.parse_args()
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "topic": "respiratory_forecast",
        "feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION,
        "validation_status": "internal_only",
        "performance": {"auc": None, "sensitivity": None, "lead_time_hours": None},
        "shap": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": "Placeholder metadata; final thresholds and performance require PI/statistician review.",
    }
    (out / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out / "metadata.json"))


if __name__ == "__main__":
    main()
