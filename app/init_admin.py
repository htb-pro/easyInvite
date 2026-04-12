import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from models import User,Role
from Routers.loging import hash_password
import os 
from dotenv import load_dotenv

load_dotenv()
pwd = os.getenv("pwd")
email = os.getenv("email")

async def ensure_admin_role(db:AsyncSession):
    admin_role_res = await db.execute(select(Role).where(Role.name == "admin"))
    admin_role = admin_role_res.scalars().first()
    if not admin_role:
        new_admin_role = Role(
            name = "admin"
        )
        db.add(new_admin_role)
        await db.commit()
        await db.refresh(new_admin_role)
        return new_admin_role
    return admin_role

async def create_admin(db:AsyncSession): 
    admin_role =await ensure_admin_role(db)
    existing_adm_res = await db.execute(select(User).where(User.email == email).options(selectinload(User.roles)))
    existing_adm = existing_adm_res.scalars().first() 
    if existing_adm:
        print("admin deja existant")
        return #si un admin existe deja on ne le cree pas 
    
    print("Role admin introuvable")
    init_admin = User(
    name = "htb-pro",
    email = email,
    password = hash_password(pwd)
    )
    init_admin.roles.append(admin_role)
    db.add(init_admin)
    await db.commit()
    await db.refresh(init_admin)
    print("admin created ")
    return
    

