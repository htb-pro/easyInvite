#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Depends,APIRouter,Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import models
from db_setting import engine,connecting
from models import *
from datetime import date
from typing import Optional
from datetime import datetime,date
from sqlalchemy.orm import Session
from utils.Qr_Utils.qrCodeUtils import createInviteQrCode
models.Base.metadata.create_all(bind=engine)
import os 

Root = APIRouter()
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
@Root.get('/invite/{event_id}/{guest_id}/create')
def getGuestInvite(request:Request,event_id:str ,guest_id : str ,db:Session = Depends(connecting)):
    guestInvite = db.query(Guest).filter(Guest.id == guest_id, Guest.event_id == event_id).first()
    return templates.TemplateResponse("Invitation/show_invite/invite.html",{'request':request,"guest":guestInvite})
@Root.get('/get_invite',name="invitation",response_class=HTMLResponse)#get the invite url
def getInvite(request:Request):
    return templates.TemplateResponse("Invitation/List/list.html",{'request':request})