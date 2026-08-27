import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.config import AppConfig
from pymongo import AsyncMongoClient

async def main():
    cfg = AppConfig()
    s = cfg.settings
    if s.SMARTCARE_DB_USER:
        uri = f"mongodb://{s.SMARTCARE_DB_USER}:{s.SMARTCARE_DB_PASSWORD}@{s.SMARTCARE_DB_HOST}:{s.SMARTCARE_DB_PORT}/{s.SMARTCARE_DB_AUTH}"
    else:
        uri = f"mongodb://{s.SMARTCARE_DB_HOST}:{s.SMARTCARE_DB_PORT}/"
    db_name = s.SMARTCARE_DB_NAME or cfg.yaml_cfg.get("databases",{}).get("smartcare",{}).get("database","SmartCare")
    client = AsyncMongoClient(uri)
    db = client[db_name]

    # Check account collection for user 301126
    col = db["account"]
    print("=== account collection for 301126 ===")
    doc = await col.find_one({"$or": [{"userName": "301126"}, {"username": "301126"}, {"account": "301126"}, {"loginName": "301126"}, {"工号": "301126"}]})
    if doc:
        for k, v in doc.items():
            print(f"  {k}: {v!r}")
    else:
        print("  NOT FOUND in account collection")

    # Check what dept names exist for the admitted patients
    print("\n=== deptCode -> dept name mapping (admitted) ===")
    col2 = db["patient"]
    pipeline = [
        {"$match": {"status": "admitted"}},
        {"$group": {"_id": {"deptCode": "$deptCode", "dept": "$dept"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    cursor = await col2.aggregate(pipeline)
    async for doc in cursor:
        g = doc['_id']
        print(f"  deptCode={g.get('deptCode')!r} -> dept={g.get('dept')!r}: {doc['count']}")

    await client.close()

asyncio.run(main())
