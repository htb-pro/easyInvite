#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,Cookie,status
from fastapi.responses import JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import models,pyotp,time
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
    # 1. Nettoyage de sécurité sur la chaîne reçue du scanner
    qr_data = qr_data.strip()
    
    # Validation du préfixe de la plateforme
    if qr_data.startswith("EI~"):
        try:
            # Découpage du QR code (Format attendu : EI~ID_BILLET~TOKEN_TOTP)
            parts = qr_data.split("~")
            if len(parts) != 3:
                return {"valid": False, "is_scanned": False, "message": "Format de QR code invalide."}
            
            prefix, ticket_id, scanned_token = parts
            
            # 2. Récupération asynchrone du billet dans la base de données
            result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
            ticket = result.scalars().first()

            # Si le billet n'existe pas
            if not ticket:
                return {"valid": False, "is_scanned": False, "message": "Billet introuvable."}
            
            # 3. Vérification anti-fraude : le billet a-t-il déjà été utilisé ?
            if ticket.is_scanned is True:
                return {
                    "valid": True, 
                    "is_scanned": True, 
                    "state": True, 
                    "message": "⚠️ Ce billet a déjà été validé et utilisé."
                }

            # 4. Nettoyage de la clé Base32 (Sécurité contre les erreurs de caractères 0/O et 1/I)
            secret_propre = ticket.totp_secret.upper().strip().replace('0', 'O').replace('1', 'I')
            
            # 5. Initialisation de l'algorithme TOTP avec la clé propre
            totp = pyotp.TOTP(secret_propre, interval=30)

            # Synchronisation temporelle basée sur le timestamp de la machine
            timestamp_local = int(time.time())
            # 6. Vérification du token avec une fenêtre de tolérance (valid_window=4)
            if totp.verify(scanned_token, for_time=timestamp_local, valid_window=4):
                
                # Validation validée ! On marque immédiatement le billet comme scanné
                ticket.is_scanned = True 
                
                # Sauvegarde immédiate en base de données (AWAIT obligatoire)
                await db.commit()
                
                # Récupération sécurisée des attributs du billet pour l'affichage au guichet
                participant = getattr(ticket, "name", "Détenteur du billet")
                type_billet = getattr(ticket, "type", "Standard")

                # ON RENVOIE "is_scanned": True ICI pour que l'UI affiche le succès au premier scan
                return {
                    "valid": True,
                    "is_scanned": False,
                    "state": False,
                    "type": "ticket",
                    "ticket_id": ticket.id,
                    "name": participant,
                    "ticket_type": type_billet,
                    "message": "✅ Billet validé avec succès ! Bienvenue."
                }
            else:
                return {"valid": False, "is_scanned": False, "message": "Code expiré. Veuillez rafraîchir le QR Code."}

        except Exception as e:
            return {"valid": False, "is_scanned": False, "message": f"Erreur lors du traitement du billet : {str(e)}"}
    #============================================================       
    #CAS B : IL S'AGIT D'UNE INVITATION CLASSIQUE (Pas de préfixe EI~)
    # =========================================================================
    else:
        try:
            # On cherche l'invité dans la table des invités à partir des données brutes du QR Code
            # (Adapte 'Guest.qr_code' ou 'Guest.id' selon le stockage de tes invitations)
            guest_id = decrypt_token(qr_data)
            result = await db.execute(select(Guest).where(Guest.id == guest_id))
            guest = result.scalars().first()
            if not guest:
                return {"valid": False, "message": "Invitation inconnue ou invalide."}
                
            # Renvoi des informations de l'invitation pour le lien cliquable JavaScript
            return {
                "valid": True,
                "type": "invitation",
                "guest_id": guest.id,
                "name": getattr(guest, "name", "Invité Spécial")
            }
            
        except Exception as e:
            return {"valid": False, "message": f"Erreur lors du traitement de l'invitation : {str(e)}"}
    
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