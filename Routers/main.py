#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Depends,APIRouter,Cookie,HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from db_setting import connecting
from sqlalchemy.ext.asyncio import AsyncSession
from models import User
from datetime import datetime,date
from Routers.loging import get_current_user_from_cookie
from jose import jwt 
from config import secret,algo
from app.security.permissions import has_permission
from Routers.template import templates

#Root = APIRouter(prefix="/admin",dependencies = [Depends(get_current_user_from_cookie)])
Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])

Root.mount("/static",StaticFiles(directory="static"), name="static")#ou sont stocker les fichier static

@Root.get("/main",name="main_page")#get the main page
async def get_main(request:Request,access_token:str=Cookie(None),current_user:User =Depends(get_current_user_from_cookie),db:AsyncSession=Depends(connecting)):
    get_email = jwt.decode(access_token,secret,algorithms = [algo])
    id = get_email.get("user")
    user_res = await db.execute(select(User).where(User.id == id))
    user = user_res.scalars().first() 
    if not user :
        raise HTTPException("Utilisateur introuvable")
    user_name = user.name
    Today = date.today()
    return templates.TemplateResponse("easyInviteApk/homePage/main.html",{'request':request,'username':user_name,'date':Today,'current_user':current_user})

#-----------------------about invitation view
@Root.get('/get_invite',name="invitation",response_class=HTMLResponse)#get the invite url
def getInvite(request:Request):
    return templates.TemplateResponse("Invitation/List/list.html",{'request':request})



