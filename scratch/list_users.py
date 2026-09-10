import sys
sys.path.insert(0, ".")
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models.user import User

async def list_users():
    async with async_session() as db:
        res = await db.execute(select(User))
        users = res.scalars().all()
        for u in users:
            print(f"User: id={u.id}, email={u.email}")

if __name__ == "__main__":
    asyncio.run(list_users())
