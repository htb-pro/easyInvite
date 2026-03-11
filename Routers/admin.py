from fastapi import Request,APIRouter,Form,Depends
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from models import Group,Role,Permission,User,Event,Guest
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload
from db_setting import connecting,AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import Group as group_schemas
from Routers.loging import get_current_user_from_cookie,admin_required


Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie),Depends(admin_required)])
templates= Jinja2Templates(directory="Templates")

@Root.get("/admin_dashboard",name="adm_dashboard")
async def get_admin_dashboard(request:Request,db:AsyncSession = Depends(connecting)):
    group_id = request.query_params.get("group_id")
    async with AsyncSessionLocal() as session:
        event_count = await session.execute(select(func.count()).select_from(Event))#Nombre des  items enregistrer
        actif_event_count = await session.execute(select(func.count()).select_from(Event).where(Event.state == "en cours"))#Nombre des  items enregistrer
        pending_event_count = await session.execute(select(func.count()).select_from(Event).where(Event.state == "en attente"))#Nombre des  items enregistrer
        guest_count = await session.execute(select(func.count()).select_from(Guest))#Nombre des  items enregistrer
        total_event = event_count.scalar()
        total_guest = guest_count.scalar()
        total_actif_event = actif_event_count.scalar()
        total_pending_event = pending_event_count.scalar()
    query = select(Event).options(selectinload(Event.guests))
    if group_id:
        query = query.where(Event.group_id == group_id).options(selectinload(Event.guests))
    get_event_res = await db.execute(query)
    events = get_event_res.scalars().all()
    group_res= await db.execute(select(Group))
    groups = group_res.scalars().all()
    return templates.TemplateResponse("Authentification/admin/admin_dashboard.html",{'request':request,'groups':groups,'events':events,'total_event':total_event,'total_guest':total_guest,'total_actif_event':total_actif_event,'total_pending_event':total_pending_event})

@Root.get("/see_event/{event_id}")
async def get_detail_event(request:Request,event_id :str,db:AsyncSession = Depends(connecting)):
    event_res = await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.guests),selectinload(Event.groups)))
    event = event_res.scalars().first()
    return templates.TemplateResponse("Authentification/admin/event/detail_event.html",{'request':request,'event':event})

@Root.get("/admin_list_event",name = "adm_list_event")
async def get_event_list(request:Request,db:AsyncSession = Depends(connecting)):
    event_name =request.query_params.get('event_name')
    query = select(Event).options(selectinload(Event.groups),selectinload(Event.guests))
    if event_name:
        query = query.where(Event.name == event_name)
    event_res = await db.execute(query)
    events = event_res.scalars().all()
    return templates.TemplateResponse("Authentification/admin/event/list.html",{'request':request,'events':events})

@Root.get("/access_management/create_form",name = "access_manager")
def get_create_groupe_form(request:Request):
    existing_group = request.session.pop('group_existing_message',None)
    existing_role = request.session.pop('role_existing_message',None)
    existing_perms = request.session.pop('perms_existing_message',None)
    return templates.TemplateResponse("Authentification/forms/roles_and_perms_form.html",{'request':request,'group_existing_message':existing_group,'existing_role':existing_role,'existing_perms':existing_perms})

@Root.post("/create_group")#la creation d'un groupe
async def create_group(request:Request,group_name: str = Form(...),db:AsyncSession = Depends(connecting)):
    group_res =await  db.execute(select(Group).where(Group.name==group_name))
    group = group_res.scalars().first()
    message = None
    if group:
        message = "un group exist avec ce nom "
        request.session['group_existing_message'] = message
        return RedirectResponse("/access_management/create_form",303)
    new_group = Group(
        name = group_name
    )
    db.add(new_group)
    await db.commit()
    await db.refresh(new_group)
    return RedirectResponse("/access_management/create_form",303)

@Root.post("/create_role")#la creation d'un role
async def create_group(request:Request,role_name: str = Form(...),db:AsyncSession = Depends(connecting)):
    role_res =await  db.execute(select(Role).where(Role.name==role_name))
    role = role_res.scalars().first()
    message = None
    if role:
        message = "un group exist avec ce nom "
        request.session['role_existing_message'] = message
        return RedirectResponse("/access_management/create_form",303)
    new_role = Role(
        name = role_name
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)
    return RedirectResponse("/access_management/create_form",303)

@Root.post("/create_permission")#la creation d'un role
async def create_group(request:Request,permission_name: str = Form(...),db:AsyncSession = Depends(connecting)):
    perm_res =await  db.execute(select(Permission).where(Permission.name==permission_name))
    permission = perm_res.scalars().first()
    message = None
    if permission:
        message ="cette permission exist deja "
        request.session['perms_existing_message'] = message
        return RedirectResponse("/access_management/create_form",303)
    new_perm = Permission(
        name = permission_name
    )
    db.add(new_perm)
    await db.commit()
    await db.refresh(new_perm)
    return RedirectResponse("/access_management/create_form",303)

@Root.get("/permission_assigning/form",name="assign")
async def assign_form(request:Request,db:AsyncSession = Depends(connecting)):
    roles_res = await db.execute(select(Role))
    roles = roles_res.scalars().all()
    perms_res = await db.execute(select(Permission))
    permissions = perms_res.scalars().all()
    return templates.TemplateResponse("Authentification/forms/assign_permission.html",{'request':request,'roles':roles,'permissions':permissions})

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

@Root.get("/params",name="params")
async def get_params_view(request:Request):
    return templates.TemplateResponse("Authentification/admin/setting_admin_option.html",{'request':request})