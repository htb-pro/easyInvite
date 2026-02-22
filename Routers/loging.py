#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import APIRouter,Request,HTTPException,Depends,Form,status
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from datetime import datetime,timedelta
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import User
from db_setting import connecting
import os
from jose import JWTError,jwt
from config import secret,algo,token_expire_minute

templates = Jinja2Templates(directory = "Templates")
Root = APIRouter()
pwd_context = CryptContext(schemes=["argon2"],deprecated="auto")


#middleware pour la pretection des pages 
oauth_scheme =OAuth2PasswordBearer(tokenUrl = "login")
def get_curent_user(token:str = Depends(oauth_scheme)):
    user = verify_token(token)
    if not user :
        raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED,detail = "non autorisé")
    return user

#verifier le token de l'utilisateur
async def get_current_user_from_cookie(request:Request,db:AsyncSession  = Depends(connecting)):
    token = request.cookies.get("access_token")
    if not token :
        raise HTTPException(status_code = 401)
    try:
        payload = jwt.decode(token,secret,algorithms = algo)
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code = 401)
    res_user = await db.execute(select(User).where(User.email ==email))
    user = res_user.scalars().first()
    if not user :
        raise HTTPException(status_code = 404,detail = "utilisateur introuvable")
    return user

def hash_password(password:str):#methode pour le hashage du password
    return pwd_context.hash(password[:1024])

def verify_password(password:str,hashed:str):#verifier le password
    return pwd_context.verify(password,hashed)#hashed est le mot de passe contentu dans la db

def create_token(data:dict):#Creation du token
    data_to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=token_expire_minute)
    data_to_encode.update({"exp":expire})
    return jwt.encode(data_to_encode,secret,algorithm = algo)

def verify_token(token:str):#verification du token
    try:
        payload = jwt.decode(token,secret,algorithms = [algo])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401,"token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401,"token invalide")

@Root.get("/",name="intro_link")#get the intro view
def intro_view(request:Request):
    return templates.TemplateResponse("Authentification/forms/home.html",{'request':request})

@Root.get("/list_users")#get the auth view
async def get_users(request:Request,curent_user = Depends(get_current_user_from_cookie),db:AsyncSession = Depends(connecting)):
    user_res = await db.execute(select(User)) #get the list in user
    users = user_res.scalars().all()
    message = request.session.pop('message',None)
    return templates.TemplateResponse("Authentification/admin/list_user.html",{'request':request,'users':users,'message':message})

@Root.get("/register")#get the auth view
def auth_view(request:Request):
    message = request.session.pop('message',None)
    return templates.TemplateResponse("Authentification/forms/register_user.html",{'request':request,'success_message':message})
    
@Root.post("/register")#get the auth view
async def auth_view(request:Request,name:str = Form(),email:str =Form(...),password:str = Form(...),role:str =Form(...),state:str = Form(),db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(User).where(User.email ==email))
    user = res.scalars().first()
    message = None
    if user :#si un utilisateur existe avec l'email
        message = "utilisateur existe déjà cet email"
        return templates.TemplateResponse("Authentification/forms/register_user.html",{'request':request,'failed_message':message})
    hashed_pwd = hash_password(password)
    new_user = User(
        name = name,
        email = email,
        password = hashed_pwd,
        role = role,
        state = state
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    message = "utilisateur enregistré"
    request.session['message'] = message
    return RedirectResponse(url="/register",status_code = 303)

@Root.get("/login",name="auth")#get the auth view
def auth_view(request:Request):
    return templates.TemplateResponse("Authentification/forms/auth.html",{'request':request})

@Root.get("/logout",name="logout")#get the auth view
def logout():
    response = RedirectResponse("/login",status_code = 302)
    response.delete_cookie("access_token",path = "/")
    return response

@Root.post("/login")#get the user data
async def login(request:Request,form_data : OAuth2PasswordRequestForm = Depends(),db:AsyncSession = Depends(connecting)):
    user_email = form_data.username
    user_res = await db.execute(select(User).where(User.email == user_email))
    user = user_res.scalars().first()
    message = None
    if not user:
        message = "nom utilisateur ou mot de passe incorect"
        return templates.TemplateResponse("Authentification/forms/auth.html",{'request':request,'message':message})
    if not verify_password(form_data.password,user.password):#compare le mot de passe entree et celui dans la db
        message = "nom utilisateur ou mot de passe incorect"
        return templates.TemplateResponse("Authentification/forms/auth.html",{'request':request,'message':message})
    if user.state !="active":
        message = "compte bloquer"
        return templates.TemplateResponse("Authentification/forms/auth.html",{'request':request,'message':message})
    access_token = create_token(data={"sub":user.email}) #si l'utilisateur existe et qu'il est active on lui cree un token
    response = RedirectResponse(url="/main",status_code = 303)
    response.set_cookie(key="access_token",value=access_token,httponly=True)
    return response

@Root.get("/user/edit/{user_id}")#endpoint pour la modification d'un user
async def edit_user(request:Request,user_id:str,db:AsyncSession = Depends(connecting)):
    get_user_to_edit = await db.execute(select(User).where(User.id == user_id))#trouver le user
    user = get_user_to_edit.scalars().first()#prendre la premiere ocurence
    if not user :
        raise HTTPException(404,"l'utilisateur n\'existe pas ")
    userName = user.name
    userEmail = user.email
    userRole = user.role
    userState = user.state
    user_id = user.id
    return templates.TemplateResponse("Authentification/forms/edit_user_form.html",{'request':request,'user_id':user_id,'userName':userName,'userEmail':userEmail,'userRole':userRole,'userState':userState})

@Root.post("/user/edit/{user_id}")#endpoint pour la modification d'un user
async def edit_user(request:Request,user_id:str,name:str = Form(),email:str = Form(),role:str = Form(),state:str = Form(),db:AsyncSession = Depends(connecting)):
    get_user_to_edit = await db.execute(select(User).where(User.id == user_id))#trouver le user
    user = get_user_to_edit.scalars().first()#prendre la premiere ocurence
    if not user :
        raise HTTPException(404,"l'utilisateur n\'existe pas ")
    user.name = name
    user.email = email
    user.role=role
    user.state = state
    await db.commit()
    message = "utilisateur modifié"
    request.session['message'] = message
    return RedirectResponse("/list_users",303)



