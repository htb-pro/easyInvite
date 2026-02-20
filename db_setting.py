from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker,AsyncSession
from dotenv import load_dotenv
import os,asyncio
#---------------------initialising
Base = declarative_base() #-----------------la classe mere pour la creation de table

load_dotenv()
DB_URL =os.getenv('db_url')
engine = create_async_engine(
    DB_URL,
    echo =True,
    #pool_pre_ping =True,
    future = True
)
        
AsyncSessionLocal = async_sessionmaker(#creation de la session
    bind=engine,
    autocommit = False,
    autoflush = False,
    class_=AsyncSession,
    expire_on_commit=False,
)
async def connecting() -> AsyncSession:
    async with AsyncSessionLocal() as session :
        yield session

async def init_db():
    async with engine.begin() as conn :
        await conn.run_sync(Base.metadata.create_all)
        print("table crees avec succe")