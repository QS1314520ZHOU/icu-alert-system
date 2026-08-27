import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import yaml
from pymongo import AsyncMongoClient

async def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    db_cfg = cfg.get("databases", cfg.get("database", {}))
    sc = db_cfg.get("smartcare", {})
    host = sc.get("host", "127.0.0.1")
    port = sc.get("port", 27017)
    db_name = sc.get("database", "SmartCare")
    user = sc.get("username", "")
    pwd = sc.get("password", "")
    auth_db = sc.get("auth_database", "admin")

    if user:
        uri = f"mongodb://{user}:{pwd}@{host}:{port}/{auth_db}"
    else:
        uri = f"mongodb://{host}:{port}/"
    
    print(f"Connecting to: mongodb://{host}:{port}/{db_name}")
    client = AsyncMongoClient(uri)
    db = client[db_name]
    col = db["patient"]
    
    # Count total
    total = await col.count_documents({})
    print(f"\nTotal patients in collection: {total}")
    
    # Count by status
    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    cursor = col.aggregate(pipeline)
    print("\n=== Patient statuses ===")
    async for doc in cursor:
        print(f"  status={doc['_id']!r}: {doc['count']}")
    
    # Sample first doc
    print("\n=== Sample patient (first 3) ===")
    async for doc in col.find().limit(3):
        sid = doc.get("_id")
        print(f"  _id={sid}, status={doc.get('status')!r}, dept={doc.get('hisDept') or doc.get('dept')}, bed={doc.get('hisBed')}")
        # Show all top-level keys
        print(f"    keys: {sorted(doc.keys())}")

    # Test the actual query the frontend uses
    in_dept = ["admitted", "在科", "住院", "icu", "icu在科"]
    q = {"status": {"$in": in_dept}}
    count_in = await col.count_documents(q)
    print(f"\nPatients matching in_dept query: {count_in}")

    await client.close()

asyncio.run(main())
