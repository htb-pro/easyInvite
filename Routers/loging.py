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
from models import User,Role
from db_setting import connecting
import os
from jose import JWTError,jwt
from config import secret,algo,token_expire_minute
from schemas import User as user_schemas

templates = Jinja2Templates(directory ="Templates")
pwd_context = CryptContext(schemes=["argon2"],deprecated="auto")
Root = APIRouter()
#verifier le token de l'utilisateur
async def get_current_user_from_cookie(request:Request,db:AsyncSession = Depends(connecting)):
    token = request.cookies.get("access_token") #recuperer le token 
    if not token :
        raise HTTPException(status_code = 401,detail="Non authenfier")
    try:
        payload = jwt.decode(token,secret,algorithms = algo)
        user_id = payload.get("user")#user est la variable contenant l'id envoyer par le token
        if user_id is None :
            raise HTTPException(status_code = 401,detail = "token invalide")
    except JWTError:
        raise HTTPException(status_code = 401,detail = "token invalide")
    user_res = await db.execute(select(User).options(selectinload(User.roles)).where(User.id == user_id).options(selectinload(User.roles).selectinload(Role.permissions)))
    user = user_res.scalars().first()
    if not user :
        raise HTTPException(status_code = 404,detail = "utilisateur introuvable")
    return user

#methode verifier le role pour acceder a une vue 
async def admin_required(user:user_schemas = Depends(get_current_user_from_cookie)):
    if not any(role.name == "admin" for role in user.roles):
        raise HTTPException(status_code = 403,detail="accès refusé")
    return user

#middleware pour la pretection des pages 
oauth_scheme =OAuth2PasswordBearer(tokenUrl = "login")
def get_curent_user(token:str = Depends(oauth_scheme)):
    user = verify_token(token)
    if not user :
        raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED,detail = "non autorisé")
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
        raise HTTPException(status_code = 401,detail = "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code = 401,detail = "token invalide")

@Root.get("/get/auth",name="intro_link")#get the intro view
def intro_view(request:Request):
    return templates.TemplateResponse("Authentification/forms/home.html",{'request':request})

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
    user_id = user.id
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
    access_token = create_token(data={"user":user_id}) #si l'utilisateur existe et qu'il est active on lui cree un token
    response = RedirectResponse(url="/main",status_code = 303)
    response.set_cookie(key="access_token",value=access_token,httponly=True)
    return response


