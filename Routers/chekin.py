#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,Cookie
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import models
from db_setting import connecting
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import *
from Routers.loging import get_current_user_from_cookie
from config import secret,algo
from jose import jwt 

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static

# @Root.get("/scan",name="scaning",response_class=HTMLResponse)#get the scan view
# def scan_view(request:Request):
#     return templates.TemplateResponse("easyInviteApk/scanQrCode/verifying.html",{'request':request})

def extract_value(value): #methode de conversion pour recuperer l'id qu'il soit dans une chaine(url) ou seul
        value = str(value).strip()
        if "/" in value:
            return value.rstrip('/').split("/")[-2]
        return value

@Root.get("/scan_view",name="scanning")#test scan
def scanQrCode(request:Request):
    return templates.TemplateResponse("easyInviteApk/scanQrCode/scan.html",{'request':request})

@Root.get("/scan",name="scanning")#checking du scan 
async def scanQrCode(guest_id:str,access_token = Cookie(None),db:AsyncSession = Depends(connecting)):
    # current_user_res = jwt.decode(access_token,secret,algorithms=[algo])
    # current_user_id = current_user_res.get("user") 
    # user_res = await db.execute(select(User).where(User.id == current_user_id).options(selectinload(User.groups)))
    # user = user_res.scalars().first()
    # user_group =None
    # if user :
    #     for group in user.groups:
    #         group_id =group.id
    #     event_res = await db.execute(select(Event))
    #     events = event_res.scalars().all()
    # print("---------------event ",event.name)
    guest_id = extract_value(guest_id)
    res_guest = await db.execute(select(Guest).where(Guest.id == guest_id))
    is_guest_exist = res_guest.scalars().first()
    if not is_guest_exist : 
        raise HTTPException(404,"guest not found")
    token = is_guest_exist.qr_token
    get_guest =await db.execute(select(Guest).where(Guest.qr_token == token).options(selectinload(Guest.invite)))
    guest =get_guest.scalars().first()
    return JSONResponse({#renvoi un response json au navigateur
        "valid":True,
        "name":guest.name,
        "guest_id":guest.id
    })

@Root.get('/result/{guest_id}')#traitement de la request json pour la verification du guest
async def scanResult(request:Request,guest_id :str,db:AsyncSession = Depends(connecting)):
    get_guest = await db.execute(select(Guest).where(Guest.id == guest_id).options(selectinload(Guest.invite),selectinload(Guest.event)))
    guest = get_guest.scalars().first() 
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    token = guest.qr_token
    get_guest =await db.execute(select(Guest).where(Guest.qr_token == token).options(selectinload(Guest.event)))
    guest = get_guest.scalars().first()
    if guest.event.state =="en attente":
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/pendingEvent.html",{'request':request})
    if guest.event.state =="terminé" : 
         return templates.TemplateResponse("easyInviteApk/scanResult/guest/event_done.html",{'request':request})
    if guest.is_present:
        guest.is_present =False
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/used_invite.html",{'request':request})
    guest.is_present = True
    guest.invite.used_at = datetime.now()
    await db.commit()
    event_name = guest.event.name
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest,'event_name':event_name})

@Root.post("/checkIn/get_pass")
async def guest_result(request:Request,guest_getPass:str=Form(),db:AsyncSession = Depends(connecting)):
    get_guest = await db.execute(select(Guest).where(Guest.get_pass == guest_getPass).options(selectinload(Guest.event)))
    guest = get_guest.scalars().first()
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/invalid_access_code.html",{'request':request})
    if guest.event.state =="en attente":
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/pendingEvent.html",{'request':request})
    if guest.event.state =="terminé" : 
         return templates.TemplateResponse("easyInviteApk/scanResult/guest/event_done.html",{'request':request})
    if guest.is_present:
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/used_access_code.html",{'request':request}) #renvoi un message d'un qr_code deja utilise dans un template html
    guest.is_present = True
    await db.commit()
    event_name = guest.event.name
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest,"event_name":event_name})