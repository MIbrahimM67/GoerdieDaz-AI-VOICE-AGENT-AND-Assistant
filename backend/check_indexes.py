import asyncio, sys
sys.path.insert(0, '.')
from app.database import engine
from sqlalchemy import text

async def check():
    async with engine.connect() as conn:
        r = await conn.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'memories'"))
        rows = r.fetchall()
        if rows:
            for row in rows:
                print(f"{row[0]}:\n  {row[1]}\n")
        else:
            print("NO INDEXES on memories table!")
        
        # Also check constraints
        r2 = await conn.execute(text("SELECT conname, contype FROM pg_constraint WHERE conrelid = 'memories'::regclass"))
        rows2 = r2.fetchall()
        if rows2:
            print("Constraints:")
            for row in rows2:
                print(f"  {row[0]} (type={row[1]})")
        else:
            print("NO CONSTRAINTS on memories table!")

asyncio.run(check())
