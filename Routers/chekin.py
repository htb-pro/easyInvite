#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter
from fastapi.responses import HTMLResponse,RedirectResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import models
from db_setting import engine,connecting
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import *
from utils.scanQrCode.scan import scan_qr_code

Root = APIRouter()

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

# @Root.get("/scan_view",name="scanning",response_class=HTMLResponse)#test scan
# def scanQrCode(request:Request):
#     return templates.TemplateResponse("easyInviteApk/scanQrCode/verifying.html",{'request':request})

@Root.get("/scan",name="scanning")#checking du scan 
async def scanQrCode(request:Request,guest_id:str,db:AsyncSession = Depends(connecting)):
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
    get_guest = await db.execute(select(Guest).where(Guest.id == guest_id).options(selectinload(Guest.invite)))
    guest = get_guest.scalars().first() 
    if not guest :
        raise HTTPException(404,"le guest n'existe pas ")
    token = guest.qr_token
    get_guest =await db.execute(select(Guest).where(Guest.qr_token == token))
    guest = get_guest.scalars().first()
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    if guest.is_present:
        guest.is_present =False
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/used_invite.html",{'request':request})
    guestNoneCard = f"{guest.name}<->{guest.place}&{guest.qr_token}${guest.telephone}<->{guest.qr_token}" #id for guest without smartphone
    guest.is_present = True
    guest.invite.used_at = datetime.now()
    await db.commit()
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest,'NoPhoneId':guestNoneCard})

@Root.post('/checkIn/',name = "scanningView") #verification du token du guest
async def scanResult(request:Request,guest_data :str = Form(...),db:AsyncSession = Depends(connecting)):
    guest_id= extract_value(guest_data)
    res_guest = await db.execute(select(Guest).where(Guest.id == guest_id))
    is_guest_exist = res_guest.scalars().first()
    if not is_guest_exist : 
         return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    token = is_guest_exist.qr_token
    get_guest =await db.execute(select(Guest).where(Guest.qr_token == token).options(selectinload(Guest.invite)))
    guest =get_guest.scalars().first()
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    if guest.is_present:#si is_present est = true alors 
        guest.is_present =False
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/used_invite.html",{'request':request}) #renvoi un message d'un qr_code deja utilise dans un template html
    guestNoneCard = f"{guest.name}<->{guest.place}&{guest.qr_token}${guest.telephone}<->{guest.qr_token}" #id for guest without smartphone
    guest.is_present = True
    guest.invite.used_at = datetime.now()
    await db.commit()
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest,'NoPhoneId':guestNoneCard})