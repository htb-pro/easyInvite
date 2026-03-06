from fastapi import Request,APIRouter,Form,Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from models import Group,Role,Permission,User
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from db_setting import connecting
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import Group as group_schemas
from Routers.loging import get_current_user_from_cookie,admin_required

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie),Depends(admin_required)])
templates= Jinja2Templates(directory="Templates")


@Root.get("/group/create_form")
def get_create_groupe_form(request:Request):
    existing_group = request.session.pop('existing_message',None)
    return templates.TemplateResponse("Authentification/forms/create_group.html",{'request':request,'existing_message':existing_group})

@Root.post("/create_group")#la creation d'un groupe
async def create_group(request:Request,group_name: str = Form(...),db:AsyncSession = Depends(connecting)):
    group_res =await  db.execute(select(Group).where(Group.name==group_name))
    group = group_res.scalars().first()
    message = None
    if group:
        message = "un group exist avec ce nom "
        request.session['existing_message'] = message
        return RedirectResponse("/group/create_form",303)
    new_group = Group(
        name = group_name
    )
    db.add(new_group)
    await db.commit()
    await db.refresh(new_group)
    return RedirectResponse("/group/create_form",303)

@Root.get("/role/create_form")
def get_create_role_form(request:Request):
    existing_group = request.session.pop('existing_message',None)
    return templates.TemplateResponse("Authentification/forms/create_roles.html",{'request':request,'existing_message':existing_group})

@Root.post("/create_role")#la creation d'un role
async def create_group(request:Request,role_name: str = Form(...),db:AsyncSession = Depends(connecting)):
    role_res =await  db.execute(select(Role).where(Role.name==role_name))
    role = role_res.scalars().first()
    message = None
    if role:
        message = "un group exist avec ce nom "
        request.session['existing_message'] = message
        return RedirectResponse("/role/create_form",303)
    new_role = Role(
        name = role_name
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)
    return RedirectResponse("/role/create_form",303)


@Root.get("/perms/create_form")
def get_create_role_form(request:Request):
    existing_group = request.session.pop('existing_message',None)
    return templates.TemplateResponse("Authentification/forms/create_perms.html",{'request':request,'existing_message':existing_group})

@Root.post("/create_permission")#la creation d'un role
async def create_group(request:Request,permission_name: str = Form(...),db:AsyncSession = Depends(connecting)):
    perm_res =await  db.execute(select(Permission).where(Permission.name==permission_name))
    permission = perm_res.scalars().first()
    message = None
    if permission:
        message ="cette permission exist deja "
        request.session['existing_message'] = message
        return RedirectResponse("/perms/create_form",303)
    new_perm = Permission(
        name = permission_name
    )
    db.add(new_perm)
    await db.commit()
    await db.refresh(new_perm)
    return RedirectResponse("/perms/create_form",303)

@Root.get("/permission_assigning/form")
async def get_create_role_form(request:Request,db:AsyncSession = Depends(connecting)):
    existing_group = request.session.pop('existing_message',None)
    perms_res = await db.execute(select(Permission))
    roles_res = await db.execute(select(Role))
    permissions = perms_res.scalars().all()
    roles = roles_res.scalars().all()
    return templates.TemplateResponse("Authentification/forms/assign_permission.html",{'request':request,'existing_message':existing_group,'permissions':permissions,'roles':roles})

@Root.post("/assign-permissions")
async def get_roles_permissions(request:Request,role_id:str = Form([]),permission_ids:list[str] = Form([]),db:AsyncSession = Depends(connecting)):
    role_res = await db.execute(select(Role).where(Role.id ==role_id).options(selectinload(Role.permissions)))
    role = role_res.scalars().first()
    if role :
        selected_permissions_res= await db.execute(select(Permission).where(Permission.id.in_(permission_ids)))
        selected_permissions = selected_permissions_res.scalars().all()
        role.permissions = selected_permissions
        await db.commit()
    return RedirectResponse(url="/permission_assigning/form",status_code = 303)