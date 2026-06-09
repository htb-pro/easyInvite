#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,Cookie,status
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import models,pyotp
from db_setting import connecting
from sqlalchemy.orm import selectinload
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import *
from Routers.loging import get_current_user_from_cookie
from config import secret,algo
from jose import jwt 
from utils.cryptography.crypt_file import decrypt_token

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
    scan_message = request.session.pop("is_scanned_message",None)
    valid_token = request.session.pop("token_message",None)
    return templates.TemplateResponse("easyInviteApk/scanQrCode/scan.html",{'request':request,'valid_token_message':valid_token,'wrong_token_message':scan_message})

@Root.get("/scan-ticket-secure")
async def scan_ticket_secure(qr_data: str, db: AsyncSession = Depends(connecting)):
    try:
        # 1. On décrypte TOUJOURS en premier (vu que les deux types de QR sont cryptés)
        decrypted = decrypt_token(qr_data)
        
        # 2. On tente de découper pour voir si c'est le format "Ticket" (EI-ID-TOKEN)
        parts = decrypted.split("~")
        
        if len(parts) == 3 and parts[0] == "EI":
            ticket_id = parts[1]
            token_recu = parts[2]
            
            # --- CAS A : LOGIQUE TICKET ---
            result = await db.execute(
                select(Ticket)
                .where(Ticket.id == ticket_id)
                .options(selectinload(Ticket.order)) # .order ou .orders selon ton modèle
            )
            ticket = result.scalars().first()
            
            if not ticket:
                raise HTTPException(status_code=404, detail="Ce billet n'existe pas dans notre système ❌")

            # Sécurité anti-réutilisation
            if ticket.is_scanned:
                return {
                    "valid": True, 
                    "type": "ticket", 
                    "name": ticket.participator_name, 
                    "ticket_id": ticket.id,
                    "state": True  # Déjà scanné
                }

            # Validation du temps TOTP
            totp_verifier = pyotp.TOTP(ticket.totp_secret, interval=30)
            if not totp_verifier.verify(token_recu, valid_window=1):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Code expiré ou capture d'écran frauduleuse ! Accès refusé ⏱️❌"
                )

            # Validation définitive de l'entrée
            ticket.is_scanned = True
            await db.commit()
            
            return {
                "valid": True, 
                "type": "ticket", 
                "name": ticket.participator_name, 
                "ticket_id": ticket.id,
                "ticket_type": ticket.order.ticket_type if ticket.order else "Standard",
                "state": False # Premier scan réussi
            }

        # --- CAS B : LOGIQUE INVITATION SIMPLE (GUEST) ---
        # Si le décryptage a réussi mais que ce n'est pas un format "EI-...", 
        # alors la variable 'decrypted' contient directement le 'guest_id' brut !
        guest_res = await db.execute(select(Guest).where(Guest.id == decrypted))
        guest = guest_res.scalars().first()
        
        if guest:
            return {
                "valid": True, 
                "type": "guest", 
                "name": guest.name, 
                "guest_id": guest.id,
                "state": False
            }
            
        # Si le code est décryptable mais ne correspond à rien en BDD
        return {"valid": False, "message": "Code inconnu ou événement expiré ❌"}

    except HTTPException as http_e:
        # Permet de laisser passer les vraies erreurs HTTP (comme le code 400 ou 404 du ticket)
        raise http_e
    except Exception as e:
        # Si le décryptage de la toute première ligne lève une erreur (ex: QR code altéré ou externe)
        print(f"DEBUG - Erreur décryptage ou système: {str(e)}") 
        return {"valid": False, "message": "Code invalide ou altéré ❌"}

@Root.get('/invite/result/{guest_id}')#traitement de la request json pour la verification du guest
async def scanResult(request:Request,guest_id :str,db:AsyncSession = Depends(connecting)):
    get_guest = await db.execute(select(Guest).where(Guest.id == guest_id).options(selectinload(Guest.invite),selectinload(Guest.event)))
    guest = get_guest.scalars().first() 
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    token = guest.qr_token
    get_guest =await db.execute(select(Guest).where(Guest.qr_token == token).options(selectinload(Guest.event)))
    guest = get_guest.scalars().first()
    event_id = guest.event_id
    event_res = await db.execute(select(Event).join(Guest).where(Event.id == event_id,Guest.id == guest_id))
    event = event_res.scalars().first()
    invite_used_at = guest.invite.used_at
    if event.state =="en attente":
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/pendingEvent.html",{'request':request})
    if event.state =="terminé" : 
         return templates.TemplateResponse("easyInviteApk/scanResult/guest/event_done.html",{'request':request})
    if guest.is_present:
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/used_invite.html",{'request':request,'invite_used_at':invite_used_at})
    guest.is_present = True
    guest.invite.used_at = datetime.now()
    await db.commit()
    event_name = guest.event.name
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest,'event_name':event_name})

@Root.get('/ticket/result/{qr_token}')#traitement de la request json pour la verification du guest
async def scanResult(request:Request,guest_id :str,db:AsyncSession = Depends(connecting)):
    get_guest = await db.execute(select(Guest).where(Guest.id == guest_id).options(selectinload(Guest.invite),selectinload(Guest.event)))
    guest = get_guest.scalars().first() 
    if not guest :
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/notFound.html",{'request':request})
    token = guest.qr_token
    get_guest =await db.execute(select(Guest).where(Guest.qr_token == token).options(selectinload(Guest.event)))
    guest = get_guest.scalars().first()
    event_id = guest.event_id
    event_res = await db.execute(select(Event).join(Guest).where(Event.id == event_id,Guest.id == guest_id))
    event = event_res.scalars().first()
    invite_used_at = guest.invite.used_at
    if event.state =="en attente":
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/pendingEvent.html",{'request':request})
    if event.state =="terminé" : 
         return templates.TemplateResponse("easyInviteApk/scanResult/guest/event_done.html",{'request':request})
    if guest.is_present:
        return templates.TemplateResponse("easyInviteApk/scanResult/guest/used_invite.html",{'request':request,'invite_used_at':invite_used_at})
    guest.is_present = True
    guest.invite.used_at = datetime.now()
    await db.commit()
    event_name = guest.event.name
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/welcom.html",{'request':request,"guest":guest,'event_name':event_name})

@Root.post("/checkIn/get_pass")
async def guest_result(request:Request,token:str=Form(),db:AsyncSession = Depends(connecting)):
    get_guest = await db.execute(select(Guest).where(Guest.get_pass ==token).options(selectinload(Guest.event)))
    guest = get_guest.scalars().first()
    if  guest :
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
    ticket_res = await db.execute(select(Ticket).where(Ticket.get_pass == token).options(selectinload(Ticket.events),selectinload(Ticket.orders)))
    ticket = ticket_res.scalar_one_or_none()
    if ticket:
        if ticket.events.state =="en attente":
            return templates.TemplateResponse("easyInviteApk/scanResult/guest/pendingEvent.html",{'request':request})
        if ticket.events.state =="terminé" : 
            return templates.TemplateResponse("easyInviteApk/scanResult/guest/event_done.html",{'request':request})
        if ticket.is_scanned:
            request.session["is_scanned_message"] = "Ce jeton ou code d'accès est déjà utilisé"
            return RedirectResponse(url="/scan_view",status_code = 303)
        ticket.is_scanned = True
        await db.commit()
        request.session['token_message'] = f"billet {ticket.orders.ticket_type} valide"
        return RedirectResponse("/scan_view",303)
    return templates.TemplateResponse("easyInviteApk/scanResult/guest/event_notFound.html",{'request':request})