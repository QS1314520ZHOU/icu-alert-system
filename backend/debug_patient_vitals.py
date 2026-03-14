
import asyncio
from datetime import datetime, timedelta
from app.database import DatabaseManager
from app.config import get_config
from bson import ObjectId

async def debug_vitals():
    db = DatabaseManager(get_config())
    await db.connect()
    
    # 1. Find patient
    patient = await db.col('patient').find_one({'name': '封世荣'})
    if not patient:
        print("Patient not found")
        return
    
    pid_str = str(patient['_id'])
    his_pid = patient.get('hisPid') or patient.get('hisPID')
    print(f"Patient: {patient['name']}, ID: {pid_str}, HIS PID: {his_pid}")
    
    # 2. Check bedside collection for both IDs
    pids = [pid_str]
    if his_pid and his_pid not in pids:
        pids.append(his_pid)
    
    since = datetime.now() - timedelta(hours=24)
    codes = ["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_T"]
    
    cursor = db.col('bedside').find({
        "pid": {"$in": pids},
        "time": {"$gte": since}
    }).sort("time", -1).limit(10)
    
    print("\nRecent bedside records:")
    async for doc in cursor:
        print(f"Time: {doc.get('time')}, PID: {doc.get('pid')}, Code: {doc.get('code')}, Value: {doc.get('fVal') or doc.get('intVal') or doc.get('strVal')}")
        
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(debug_vitals())
