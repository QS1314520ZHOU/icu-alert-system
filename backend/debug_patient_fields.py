
import asyncio
from app.config import get_config
from app.database import DatabaseManager

async def debug_patient():
    config = get_config()
    db = DatabaseManager(config)
    await db.connect()
    
    patient = await db.col("patient").find_one({})
    if patient:
        for k, v in patient.items():
            print(f"{k}: {v} ({type(v)})")
    else:
        print("No patients found")

if __name__ == "__main__":
    asyncio.run(debug_patient())
