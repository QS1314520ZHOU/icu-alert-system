
import asyncio
import os
import yaml
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timedelta

async def debug_mongo():
    # Load config to get mongo URI
    with open('backend/config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    mongo_uri = config['system']['mongodb_uri']
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database()
    
    # 1. Find patient
    patient = await db['patient'].find_one({'name': '封世荣'})
    if not patient:
        print("Patient '封世荣' not found")
        # List some patients
        print("\nExisting patients:")
        cursor = db['patient'].find({}).limit(5)
        async for p in cursor:
            print(f"- {p.get('name')}, id: {p.get('_id')}, hisPid: {p.get('hisPid') or p.get('hisPID')}")
        return
    
    pid_str = str(patient['_id'])
    his_pid = patient.get('hisPid') or patient.get('hisPID')
    print(f"Patient: {patient['name']}, ID: {pid_str}, HIS PID: {his_pid}")
    
    # 2. Check bedside collection
    pids = [pid_str]
    if his_pid:
        pids.append(str(his_pid))
    
    print(f"Searching bedside for PIDs: {pids}")
    
    since = datetime.now() - timedelta(hours=48)
    cursor = db['bedside'].find({
        "pid": {"$in": pids},
        "time": {"$gte": since}
    }).sort("time", -1).limit(20)
    
    found = False
    print("\nRecent bedside records:")
    async for doc in cursor:
        found = True
        print(f"Time: {doc.get('time')}, PID: {doc.get('pid')}, Code: {doc.get('code')}, Value: {doc.get('fVal') or doc.get('intVal') or doc.get('strVal')}")
    
    if not found:
        print("No recent bedside records found in last 48h.")
        # Check any record
        doc = await db['bedside'].find_one({"pid": {"$in": pids}})
        if doc:
            print(f"Found at least one OLD record: Time: {doc.get('time')}, Code: {doc.get('code')}")
        else:
            print("No records AT ALL for these PIDs in bedside.")
            
    client.close()

if __name__ == "__main__":
    asyncio.run(debug_mongo())
