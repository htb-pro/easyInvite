from fastapi import Depends,HTTPException,status
from Routers.loging import get_current_user_from_cookie
from db_setting import connecting 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import User,Role

async def has_permission(user,permission_name:str):
    for role in user.roles:
        for perm in role.permissions:
            if perm.name ==permission_name:
                return True
    return False

def permission_required(permission_name:str):
    async def checker(current_user = Depends(get_current_user_from_cookie)):
        if not await has_permission(current_user,permission_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="vous n'avez pas la permission requise"
            )
        return current_user
    return checker