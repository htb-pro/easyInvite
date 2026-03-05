from fastapi import APIRouter,Depends,Request,Form,HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from db_setting import connecting
from sqlalchemy.ext.asyncio import AsyncSession
from models import User,Role,Group
from Routers.loging import get_current_user_from_cookie,hash_password,admin_required

templates = Jinja2Templates(directory="Templates")
Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie),Depends(admin_required)])

@Root.get("/list_users",name="users_list")#get the auth view
async def get_users(request:Request,db:AsyncSession = Depends(connecting)):
    user_res = await db.execute(select(User).options(selectinload(User.roles),selectinload(User.groups))) #get the list in user
    users = user_res.scalars().all()
    message = request.session.pop('message',None)
    return templates.TemplateResponse("Authentification/admin/list_user.html",{'request':request,'users':users,'message':message})
@Root.get("/detail/{user_id}")
async def getUserDetail(request:Request,user_id :str,db:AsyncSession = Depends(connecting)):
    get_user = await db.execute(select(User).where(User.id == user_id))
    user = get_user.scalars().first()
    return templates.TemplateResponse("Authentification/admin/detail.html",{'request':request,'user':user})

@Root.get("/register_user")#get the user creation vue
async def auth_view(request:Request,db:AsyncSession = Depends(connecting)):
    message = request.session.pop('message',None)
    res_role = await db.execute(select(Role))
    res_group = await db.execute(select(Group))
    roles = res_role.scalars().all()
    groupes = res_group.scalars().all()
    return templates.TemplateResponse("Authentification/forms/register_user.html",{'request':request,'success_message':message,'roles':roles,'groupes':groupes})
    
@Root.post("/register")#get the auth view
async def auth_view(request:Request,name:str = Form(),email:str =Form(...),password:str = Form(...),role_id:str =Form(...),group_id:str =Form(...),state:str = Form(),db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(User).where(User.email ==email))
    user = res.scalars().first()
    message = None
    if user :#si un utilisateur existe avec l'email
        message = "utilisateur existe déjà cet email"
        return templates.TemplateResponse("Authentification/forms/register_user.html",{'request':request,'failed_message':message})
    group_res = await db.execute(select(Group).where(Group.id == group_id))
    group = group_res.scalars().first() 
    hashed_pwd = hash_password(password)
    if role_id :
            role_res = await db.execute(select(Role).where(Role.id == role_id))
            roles = role_res.scalars().first() #recuperer les roles dans la db
    new_user = User(
        name = name,
        email = email,
        password = hashed_pwd,
        state = state,
        group = group_id,
    )
    new_user.roles.append(roles)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    message = "utilisateur enregistré"
    request.session['message'] = message
    return RedirectResponse(url="/register_user",status_code = 303)


@Root.get("/user/edit/{user_id}")#endpoint pour la modification d'un user
async def edit_user(request:Request,user_id:str,db:AsyncSession = Depends(connecting)):
    get_user_to_edit = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles),selectinload(User.groups)))#trouver le user
    res_role = await db.execute(select(Role))
    res_group = await db.execute(select(Group))
    roles = res_role.scalars().all()
    groupes = res_group.scalars().all()
    user = get_user_to_edit.scalars().first()#prendre la premiere ocurence
    if not user :
        raise HTTPException(status_code = 404,datail = "l'utilisateur n\'existe pas ")
    userName = user.name
    userEmail = user.email
    userRole = user.roles
    userGroup=user.group
    userState = user.state
    user_id = user.id
    return templates.TemplateResponse("Authentification/forms/edit_user_form.html",{'request':request,'user':user,'user_id':user_id,'userName':userName,'userEmail':userEmail,'userRole':userRole,'groupes':groupes,'roles':roles,'userGroup':userGroup,'userState':userState})

@Root.post("/user/edit/{user_id}")#endpoint pour la modification d'un user
async def edit_user(request:Request,user_id:str,name:str = Form(),email:str = Form(),role:str = Form(),group:str = Form(),state:str = Form(),db:AsyncSession = Depends(connecting)):
    get_user_to_edit = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))#trouver le user
    user = get_user_to_edit.scalars().first()#prendre la premiere ocurence
    roles_res = await db.execute(select(Role).where(Role.id == role))
    roles = roles_res.scalars().first()
    if not user :
        raise HTTPException(status_code = 404,detail ="l'utilisateur n\'existe pas ")
    user.name = name
    user.email = email
    user.group = group
    user.state = state

    user.roles=[roles]
    await db.commit()
    message = "utilisateur modifié"
    request.session['message'] = message
    return RedirectResponse("/list_users",303)

@Root.post('/delete_user/{user_id}')#root for deleting user
async def deleteGuest(request:Request,user_id:str,db:AsyncSession=Depends(connecting)):
    get_user_to_be_deleted = await db.execute(select(User).where(User.id==user_id))
    user_to_be_deleted = get_user_to_be_deleted.scalars().first()
    if not user_to_be_deleted: #si le user n'existe pas dans l'evenement
        raise HTTPException(status_code = 404,detail="invité introuvable")
    await db.delete(user_to_be_deleted)#suppresion du guest
    await db.commit()#application de modification dans la db
    return RedirectResponse(f"/list_users",status_code=303)


