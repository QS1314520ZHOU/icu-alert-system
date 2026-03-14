
import asyncio
import sys
import os

# Add parent dir to path so we can import app modules
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.config import get_config
from app.database import DatabaseManager
from datetime import datetime, timedelta

async def debug():
    cfg = get_config()
    db = DatabaseManager(cfg)
    await db.connect()
    
    patient = await db.col('patient').find_one({'name': '封世荣'})
    if not patient:
        print("Patient not found")
        return
    
    print(f"Patient ID: {patient['_id']}, hisPid: {patient.get('hisPid') or patient.get('hisPID')}")
    
    pids = [str(patient['_id'])]
    hp = patient.get('hisPid') or patient.get('hisPID')
    if hp: pids.append(str(hp))
    
    codes = ["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_nibp_d", "param_ibp_s", "param_ibp_d", "param_T"]
    
    cursor = db.col('bedside').find({
        "pid": {"$in": pids},
        "time": {"$gte": datetime.now() - timedelta(hours=48)},
        "code": {"$in": codes}
    }).sort("time", -1).limit(20)
    
    print("\nRecent records in bedside:")
    async for doc in cursor:
        print(f"Time: {doc.get('time')}, PID: {doc.get('pid')}, Code: {doc.get('code')}, Value: {doc.get('fVal') or doc.get('intVal') or doc.get('strVal')}")

    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(debug())
