from __future__ import annotations

import argparse
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _default_output_dir() -> Path:
    from app.config import AppConfig
    from app.services.local_model_paths import local_model_dir

    return local_model_dir(AppConfig(), "cql_sepsis_dir", "cql-sepsis")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train CQL sepsis policy from Mongo trajectories.")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--limit", type=int, default=50000)
    args = parser.parse_args()

    try:
        import d3rlpy  # type: ignore
    except Exception:
        print("d3rlpy is required for offline CQL training. Install it in the training environment only: pip install d3rlpy")
        return 2

    out = Path(args.output_dir) if args.output_dir else _default_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    print(f"d3rlpy {getattr(d3rlpy, '__version__', 'unknown')} available; export target: {out}")
    print("Trajectory extraction is deployment-specific; wire Mongo aggregation here before production training.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
