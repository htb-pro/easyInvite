#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Depends,APIRouter,HTTPException
from fastapi.responses import HTMLResponse,StreamingResponse
from fastapi.templating import Jinja2Templates
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
@Root.get('/invite/{event_id}/{guest_id}/create')
def getGuestInvite(request:Request,event_id:str ,guest_id : str ,db:Session = Depends(connecting)):
    guestInvite = db.query(Guest).filter(Guest.id == guest_id, Guest.event_id == event_id).first()
    return templates.TemplateResponse("Invitation/show_invite/invite.html",{'request':request,"guest":guestInvite})

@Root.get('/get_invite',name="invitation",response_class=HTMLResponse)#get the invite url
def getInvite(request:Request):
    return templates.TemplateResponse("Invitation/List/list.html",{'request':request})

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