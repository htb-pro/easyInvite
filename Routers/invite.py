#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Depends,APIRouter,HTTPException,Form
from fastapi.responses import HTMLResponse,StreamingResponse,RedirectResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime,timedelta,date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_
import models
from db_setting import engine,connecting
from models import *
from sqlalchemy.orm import selectinload
import io ,urllib.parse
import zipfile
from utils.Qr_Utils.qrCodeUtils import createInviteQrCode
from pathlib import Path
from utils.Qr_Utils.qrCodeUtils import createInviteQrCode

Root = APIRouter()
picture_dirs = Path("static/Pictures/{None}/")

templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
def get_event_deadline(event_date:datetime): #setting a deadline
    deadline = event_date - timedelta(days=2)
    return deadline

def get_day(dt:datetime):
    if not dt:
        return ""
    days = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
    # dt.weekday() donne un chiffre de 0 à 6
    days_name = days[dt.weekday()]
    return f"{days_name}"
def get_month(dt:datetime):
    if not dt:
        return ""
    months = ["janvier","février","mars","avril","mai","juin","juillet","août","septembre","octobre","novembre","décembre"]
    # dt.month donne un chiffre de 1 à 12
    months_name = months[dt.month - 1]
    return f"{months_name}"

@Root.get("/qr/{event_id}/{guest_id}")
async def get_qr_img(event_id:str,guest_id:str):
    qr_image = createInviteQrCode(event_id,guest_id)
    return StreamingResponse(qr_image,media_type = "image/png") 

@Root.get('/invite/{event_id}/{guest_id}/create')#endpoint pour la l'invitation
async def getGuestInvite(request:Request,event_id:str ,guest_id : str ,db:AsyncSession = Depends(connecting)):
    get_guest_invite =await db.execute(select(Guest).where(Guest.id ==guest_id,Guest.event_id == event_id).options(selectinload(Guest.invite),selectinload(Guest.event))) #prepare le guest et son invite
    guestInvite =get_guest_invite.scalars().first() #le guest 
    event = guestInvite.event if guestInvite else None 
    invite = guestInvite.invite if guestInvite else None #l'invite
    event_img = event.type if event else None
    if not event:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html",{'request':request})
    safe_location = urllib.parse.quote(event.address)# 2. On encode l'adresse pour l'URL (remplace les espaces par des %20, etc.)
    # 3. On génère le lien Google Maps complet
    google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin=My+location&destination={safe_location}"
    copyright = datetime.now()
    event_img = event.photo_url
    event_type = event.type#type d'evenement
    if not event_id:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html",{'request':request})
    if not event_img and event.type == "Mariage":#s'il n'ya pas d'image et que c'est un mariage on affiche le template sans image
        if event.language == "en":
            return templates.TemplateResponse("Invitation/show_invite/wedding_event/en_wedding_event.html",{'request':request,'guest':guestInvite,'invite':invite,'event':event,'copyright':copyright,'google_map':google_maps_url})
        return templates.TemplateResponse("Invitation/show_invite/wedding_event/wedding_event.html",{'request':request,'guest':guestInvite,'invite':invite,'event':event,'copyright':copyright,'event_day':get_day(event.date),'event_month':get_month(event.date),'google_map':google_maps_url})
    try:
        does_event_exist= guestInvite.event.type
    except:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html",{'request':request})
    if event_type == "Mariage": #si c'est un mariage et qu'il y a une image on affiche le template avec l'image
        if event.language == "en": #si la langue de l'evenement est anglais on affiche le template en anglais sinon en francais
            return templates.TemplateResponse("Invitation/show_invite/wedding_event/en_wedding_event.html",{'request':request,'guest':guestInvite,'invite':invite,'event':event,'copyright':copyright,"event_img":event_img,'google_map':google_maps_url})
        return templates.TemplateResponse("Invitation/show_invite/wedding_event/wedding_event.html",{'request':request,'guest':guestInvite,'invite':invite,'event':event,'copyright':copyright,"event_img":event_img,'event_day':get_day(event.date),'event_month':get_month(event.date),'google_map':google_maps_url})
    # elif event_type == "Concours":
    #     return templates.TemplateResponse("Invitation/show_invite/concours_event/concours_invite.html",{'request':request,'guest':guestInvite,'event':event,'copyright':copyright,'serie_number':serie_number,'ticket_number':ticket_number})


@Root.get('/get_invite',name="invitation",response_class=HTMLResponse)#get the invite url
def getInvite(request:Request):
    return templates.TemplateResponse("Invitation/List/list.html",{'request':request})

@Root.get("/presence/confirmation/{guest_id}/{event_id}")
async def confirm_presence(request:Request,guest_id : str,event_id:str,db:AsyncSession = Depends(connecting)):
    get_guest = (select(Guest).where(Guest.id == guest_id,Guest.event_id == event_id).options(selectinload(Guest.invite).selectinload(Invite.guestResponse),selectinload(Guest.event)))
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    event_res = await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.guests)))
    event = event_res.scalars().first()
    get_message = request.session.pop("message",None) #recupere le message envoye par post
    year = datetime.now().year
    if not guest:
        raise HTTPException(404,"guest not found")
    if not event:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html",{'request':request})
    event_img = event.photo_url if event.photo_url else None
    if not event_id:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html",{'request':request})
    if not event_img and event.type == "Mariage":
        if event.language == "en":
            return templates.TemplateResponse("Invitation/show_invite/en_presence_confirmation.html",{'request':request,"guest":guest,"event":event,'message':get_message,"copyright":year})
        return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html",{'request':request,"guest":guest,"event":event,'message':get_message,"copyright":year})
    if event.language == "en":
        return templates.TemplateResponse("Invitation/show_invite/en_presence_confirmation.html",{'request':request,"guest":guest,"event":event,'message':get_message,"copyright":year})
    return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html",{'request':request,"guest":guest,"event":event,'message':get_message,'event_img':event_img,"copyright":year})

@Root.post("/presence/confirmation/{guest_id}/{event_id}")
async def GuestResponse(request:Request,guest_id:str ,event_id : str, response : str =Form(...),
                        db:AsyncSession = Depends(connecting)):
    get_guest = (select(Guest).where(Guest.id == guest_id,Guest.event_id == event_id).options(selectinload(Guest.event),selectinload(Guest.invite)))
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    event_res = await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.guests)))
    event = event_res.scalars().first()
    message = ""
    today = datetime.now()
    year = today.year
    event_date = guest.event.date
    deadline = get_event_deadline(event_date)
    event_img_path = None
    if not guest : #if the guest exist
        raise HTTPException(404,"l'invité introuvable")
    if not event:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html",{'request':request})
    if today >  get_event_deadline(event_date):
       message = "la date limite pour la confirmation est dépassée"
       return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html",{'request':request,'guest':guest,"event":event,'is_img_exist':images,'event_img':event_img_path,'message':message,'deadline':deadline.isoformat()})
    get_response = select(PresenceConfirmation).where(PresenceConfirmation.guest_id == guest_id) #get data of guest in presenceconfirmation
    response_result =await db.execute(get_response)
    exist_response = response_result.scalars().first() #get data of guest in presenceconfirmation
    if exist_response: #if the guest has already the response 
        #update
        exist_response.guest_id = guest_id
        exist_response.invite_id = guest.invite.id
        exist_response.response = response
        exist_response.send_at = datetime.utcnow()
        if event.language == "en":
            message = "✅ Your response has been updated."
        else:
            message =  "✅ Votre réponse a été mise à jour."
        await db.commit()
    else: 
        #create a new one
        presence = PresenceConfirmation(
            guest_id = guest_id,
            invite_id = guest.invite.id, 
            response = response
        )
        db.add(presence)
        await db.commit()
        await db.refresh(presence)
        if event.language == "en":
            message = "🎉 Your presence has been registered."
        else:
            message = "🎉 Votre présence a été enregistrée."
    request.session['message'] =message # prendre le message est l'envoyer vers get 
    return RedirectResponse(f'/presence/confirmation/{guest_id}/{event_id}',status_code = 303)

@Root.get("/download/invite/{event_id}/{guest_id}")#telecharger une invitation
async def get_guest_invite(event_id:str,guest_id :str,db:AsyncSession =Depends(connecting)):
    get_guest = select(Guest).where(Guest.id == guest_id,Guest.event_id == event_id)
    res = await db.execute(get_guest)
    guest = res.scalars().first()
    guest_name = guest.name
    event = event_id
    guest_id = guest_id
    phone = guest.telephone
    guest_phone = phone[:-4] +"xxxx"
    buffer = createInviteQrCode(event,guest_id)
    return StreamingResponse(buffer,media_type = "image/png",headers = {"content-Disposition":f"attachment;filename=event_{guest_name}-{guest_phone}.png"})
@Root.get('/download/invite/{event_id}')#telecharger toutes les invitations(Qrcodes)
async def getInviteFile(event_id:str,db:AsyncSession = Depends(connecting)):
    invites = select(Invite).where(Invite.event_id == event_id).options(selectinload(Invite.guest).selectinload(Guest.event))
    res = await db.execute(invites)
    event_guests = res.scalars().all()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer,"w") as zip_file:
        for guest in event_guests :
            event_name = guest.guest.event.name
            guest_id = guest.guest.id #prendre l'id du guest 
            guest_name = guest.guest.name #prendre le nom de l'invite pour la construction du nom de fichier
            guest_tel = guest.guest.telephone#prendre le numero tel de l'invite pour la construction du nom de fichier
            qr_buffer = createInviteQrCode(event_id,guest_id)#generate the guest invite qr_code
            masqued_guest_tel = guest_tel[:-4]+'xxxx'
            filename = f"{guest_name}-{masqued_guest_tel}.png" #Invite token 
            zip_file.writestr(filename,qr_buffer.getvalue())
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer,media_type = "application/x-zip-compresed",headers = {"content-Disposition":f"attachment;filename=event_{event_name}_invitations.zip"})

    get_guest = select(Guest).where(Guest.id == guest_id,Guest.event_id == event_id)
    res = await db.execute(get_guest)
    guest = res.scalars().first()
    guest_token = guest.qr_token
    guest_name = guest.name
    if not guest :
        raise HTTPException(404,"invité n'existe pas")
    memory = createQrCode(guest_token)
    return StreamingResponse(memory,media_type = "image/png",headers={"content-Disposition":f"attachment;filename={guest_name}.png"})