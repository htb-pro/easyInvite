import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import User,Role
from Routers.loging import hash_password
import os 
from dotenv import load_dotenv

load_dotenv()
pwd = os.getenv("pwd")
email = os.getenv("email")

async def create_admin(db):
    existing_adm_res = await db.execute(select(User).where(User.email == email).options(selectinload(User.roles)))
    existing_adm = existing_adm_res.scalars().first()
    if existing_adm:
        print("admin deja existant")
        return #si un admin existe deja on ne le cree pas 
    admin_role_res = await db.execute(select(Role).where(Role.name == "admin"))
    admin_role = admin_role_res.scalars().first()
    if not admin_role:
        print("Role admin introuvable")
        return
    init_admin = User(
        email = email,
        password = hash_password(pwd)
    )
    init_admin.roles.append(admin_role)
    db.add(init_admin)
    await db.commit()
    await db.refresh(init_admin)
    print("admin created ")

