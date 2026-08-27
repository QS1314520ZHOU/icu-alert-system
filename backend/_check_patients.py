import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.config import settings
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB or 'icu_alert']
    col = db['patient']

    pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    cursor = col.aggregate(pipeline)
    print("=== Patient statuses ===")
    async for doc in cursor:
        print(f"  status={doc['_id']!r}: {doc['count']}")

    print("\n=== Sample patient (first 3) ===")
    async for doc in col.find().limit(3):
        print(f"  _id={doc.get('_id')}, status={doc.get('status')}, dept={doc.get('hisDept') or doc.get('dept')}, bed={doc.get('hisBed')}")
        print(f"    keys: {list(doc.keys())[:20]}")

asyncio.run(main())
