import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from models import User,Role,Permission
from Routers.loging import hash_password
import os 
from dotenv import load_dotenv

load_dotenv()
pwd = os.getenv("pwd")
email = os.getenv("email")

ADMIN_PERMISSIONS = ["create_event","view_event", "edit_event","delete_event", "create_guest", "view_guest", "edit_guest", "delete_guest","create_ticket", "view_ticket", "edit_ticket", "delete_ticket","create_order", "confirm_order","view_order", "edit_order", "delete_order",]

async def ensure_admin_role(db: AsyncSession):
    # 1. Récupérer ou créer le rôle Admin
    admin_role_res = await db.execute(
        select(Role).where(Role.name == "admin").options(selectinload(Role.permissions)) # On charge les permissions existantes
    )
    admin_role = admin_role_res.scalars().first()
    
    if not admin_role:
        admin_role = Role(name="admin")
        db.add(admin_role)
        await db.commit()
        await db.refresh(admin_role, ["permissions"])

    # 2. Gestion et association des droits/permissions
    for perm_name in ADMIN_PERMISSIONS:
        # On vérifie si la permission existe globalement en BDD
        perm_res = await db.execute(select(Permission).where(Permission.name == perm_name))
        permission = perm_res.scalars().first()
        
        # Si la permission n'existe pas du tout en BDD, on la crée
        if not permission:
            permission = Permission(name=perm_name)
            db.add(permission)
            await db.flush() # Flush pour avoir l'ID sans casser la transaction globale
            
        # Si le rôle admin ne possède pas encore cette permission, on lui ajoute
        if permission not in admin_role.permissions:
            admin_role.permissions.append(permission)

    # On valide toutes les associations de droits d'un coup
    await db.commit()
    await db.refresh(admin_role)
    return admin_role

async def create_admin(db: AsyncSession): 
    admin_role = await ensure_admin_role(db)
    
    existing_adm_res = await db.execute(
        select(User).where(User.email == email).options(selectinload(User.roles))
    )
    existing_adm = existing_adm_res.scalars().first() 
    
    if existing_adm:
        print("⚡ Admin déjà existant en base de données.")
        return 
    
    # Création du super-utilisateur initial
    init_admin = User(
        name="htb-pro",
        email=email,
        password=hash_password(pwd)
    )
    
    # On lui attribue le rôle admin (qui a déjà tous ses droits)
    init_admin.roles.append(admin_role)
    
    db.add(init_admin)
    await db.commit()
    await db.refresh(init_admin)
    print("🚀 Admin créé avec succès et équipé de tous ses droits !")
    return

