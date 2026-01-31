#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import models
from db_setting import engine,connecting
from sqlalchemy.orm import Session
from models import *
from utils.scanQrCode.scan import scan_qr_code

models.Base.metadata.create_all(bind=engine)

Root = APIRouter()

templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static


# @Root.get("/scan",name="scaning",response_class=HTMLResponse)#get the scan view
# def scan_view(request:Request):
#     return templates.TemplateResponse("easyInviteApk/scanQrCode/verifying.html",{'request':request})

@Root.get("/scan",name="scanning",response_class=HTMLResponse)
def scanQrCode(request:Request):
    return templates.TemplateResponse("easyInviteApk/scanQrCode/verifying.html",{'request':request})

@Root.post('/checkIn/',name = "scanningView")
def scanResult(request:Request,qr_token :str = Form(...),db:Session = Depends(connecting)):
    token = qr_token.split('/')[-1]
    guest = db.query(Guest).filter(Guest.qr_token == token).first()
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    if guest.is_present:
        guest.is_present =False
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/guestResult.html",{'request':request})
    guest.is_present = True
    guest.invite.used_at = datetime.now()
    db.commit()
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest})