import sys
sys.path.insert(0, ".")
import asyncio
from sqlalchemy import select
from app.database import async_session
from app.models.user import User
from app.models.profile import Profile
from app.models.entry import Entry
from app.models.goal import Goal

async def check_user():
    async with async_session() as db:
        u = (await db.execute(select(User).where(User.email == "anshumanr699@gmail.com"))).scalar_one_or_none()
        if not u:
            print("User not found!")
            return
        p = (await db.execute(select(Profile).where(Profile.user_id == u.id))).scalar_one_or_none()
        print("Profile for anshumanr699@gmail.com:", p.__dict__ if p else "No profile")
        
        entries = (await db.execute(select(Entry).where(Entry.user_id == u.id, Entry.deleted_at.is_(None)))).scalars().all()
        print(f"Total entries: {len(entries)}")
        for e in entries:
            print(f"  Entry: {e.category} | {e.subcategory} | {e.value} {e.unit} | {e.occurred_at}")

        goals = (await db.execute(select(Goal).where(Goal.user_id == u.id, Goal.deleted_at.is_(None)))).scalars().all()
        print(f"Total goals: {len(goals)}")
        for g in goals:
            print(f"  Goal: {g.name} | {g.current_value}/{g.target_value} {g.unit}")

if __name__ == "__main__":
    asyncio.run(check_user())
