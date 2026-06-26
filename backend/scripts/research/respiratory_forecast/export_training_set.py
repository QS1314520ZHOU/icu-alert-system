from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta

from app.alert_engine.features.respiratory_features import RESPIRATORY_FEATURE_SCHEMA_VERSION, build_respiratory_forecast_features
from app.config import AppConfig
from app.database import MongoDB
from app.data_adapters.mongo_adapter import MongoClinicalDataAdapter


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export respiratory forecast feature rows using the shared online feature builder.")
    parser.add_argument("--hours", type=int, default=12)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    cfg = AppConfig()
    db = MongoDB(cfg)
    await db.connect()
    try:
        adapter = MongoClinicalDataAdapter(db=db)
        now = datetime.now()
        cursor = db.col("patient").find({}, {"_id": 1, "hisPid": 1, "name": 1}).limit(max(1, args.limit))
        rows = []
        async for patient in cursor:
            rows.append(await build_respiratory_forecast_features(adapter, patient, now=now, cfg={"history_hours": args.hours}))
        print({"feature_schema_version": RESPIRATORY_FEATURE_SCHEMA_VERSION, "rows": len(rows), "generated_at": now.isoformat()})
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
