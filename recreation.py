# init_db.py
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from db_setting import Base
import os 

DATABASE_URL = DB_URL =os.getenv('db_url_local')

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def recreate_tables():
    async with engine.begin() as conn:
        # Cette ligne supprime TOUTES les tables si elles existent
        await conn.run_sync(Base.metadata.drop_all)
        # Cette ligne recrée toutes les tables
        await conn.run_sync(Base.metadata.create_all)
    print("Tables recreated successfully!")

import asyncio
#asyncio.run(recreate_tables())