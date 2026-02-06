#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Depends,APIRouter,HTTPException,Form
from fastapi.responses import HTMLResponse,StreamingResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime,timedelta,date
import models
from db_setting import engine,connecting
from models import *
from sqlalchemy.orm import Session
models.Base.metadata.create_all(bind=engine)
import os 
import zipfile
import io 

Root = APIRouter()
QR_FOLDER ="static/Pictures/inviteQrCode"#where invite are
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
def get_event_deadline(event_date:date): #setting a deadline
    deadline = event_date - timedelta(days=2)
    print(deadline)
    return deadline

@Root.get('/invite/{event_id}/{guest_id}/create')
def getGuestInvite(request:Request,event_id:str ,guest_id : str ,db:Session = Depends(connecting)):
    guestInvite = db.query(Guest).filter(Guest.id == guest_id, Guest.event_id == event_id).first()
    event= event_id
    copyright = datetime.now()
    return templates.TemplateResponse("Invitation/show_invite/invite.html",{'request':request,'guest':guestInvite,'event_id':event,'copyright':copyright})

@Root.get('/get_invite',name="invitation",response_class=HTMLResponse)#get the invite url
def getInvite(request:Request):
    return templates.TemplateResponse("Invitation/List/list.html",{'request':request})

@Root.get("/presence/confirmation/{guest_id}/{event_id}")
def confirm_presence(request:Request,guest_id : str,event_id:str,db:Session = Depends(connecting)):
    guest = db.query(Guest).filter(Guest.id == guest_id,Guest.event_id ==event_id).first()
    event = event_id
    if not guest:
        raise HTTPException(404,"guest not found")
    return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html",{'request':request,"guest":guest,"event_id":event})

@Root.post("/presence/confirmation/{guest_id}/{event_id}")
def GuestResponse(request:Request,guest_id:str ,event_id : str, response : str =Form(...),db:Session = Depends(connecting)):
    guest = db.query(Guest).filter(Guest.id ==guest_id, Guest.event_id == event_id).first()
    message = ""
    today = date.today()
    event_date = guest.event.date
    if not guest : #if the guest exist
        raise HTTPException(404,"l'invité introuvable")
    if today >  get_event_deadline(event_date):
       message = "la date limite pour la confirmation est dépassée"
       return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html",{'request':request,'guest':guest,'message':message})
    exist_response = db.query(PresenceConfirmation).filter(PresenceConfirmation.guest_id == guest_id).first() #get data of guest in presenceconfirmation
    if exist_response: #if the guest has already the response 
        #update
        exist_response.guest_id = guest_id
        exist_response.invite_id = guest.invite.id
        exist_response.response = response
        exist_response.send_at = datetime.utcnow()
        message =  "✅ Votre réponse a été mise à jour."
    else: 
        #create a new one
        presence = PresenceConfirmation(
            guest_id = guest_id,
            invite_id = guest.invite.id, 
            response = response
        )
        db.add(presence)
        db.commit()
        db.refresh(presence)
        message = "🎉 Votre présence a été enregistrée."
    return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html",{'request':request,'guest':guest,'message':message})

@Root.get('/download/invite/{event_id}')
def getInviteFile(event_id:str):
    event_folder = os.path.join(QR_FOLDER,f"Event_{event_id}")
    if not os.path.exists(event_folder) or not os.path.isdir(event_folder):
        raise HTTPException(404,"evenement non trouvé")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w",zipfile.ZIP_DEFLATED) as zip_file:
        for filename in os.listdir(event_folder):
            filepath = os.path.join(event_folder,filename)
            if os.path.isfile(filepath)and filename.endswith("png"):
                zip_file.write(filepath,arcname = filename)
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer,media_type = "application/x-zip-compresed",headers = {"content-Disposition":"attachment;filename=qr_codes.zip"})