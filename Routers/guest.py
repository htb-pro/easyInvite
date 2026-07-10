#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
import json
from xmlrpc import client
from fastapi import Request,Form,Depends,HTTPException,APIRouter,Cookie,Form,UploadFile,File,BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select,and_,func,desc,asc
from uuid import uuid4
from db_setting import engine,connecting,AsyncSessionLocal
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.exc import IntegrityError
from models import *
from typing import Optional
from datetime import datetime
import cloudinary,cloudinary.uploader,requests,asyncio,secrets
from pathlib import Path
from utils.Qr_Utils.qrCodeUtils import generateInviteQrCode
import base64,urllib.parse,httpx
from Routers.loging import get_current_user_from_cookie
from app.security.permissions import permission_required
from urllib.parse import quote
from jose import jwt 
from config import secret,algo,whatsap_phone_Number_ID,whatsapp_token,account_sid,auth_token,twilio_number,text_content,media_content,set_secure_cookie,verify_csrf
from pydantic import BaseModel
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException


Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates

#--------------------About guest
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

def format_to_drc_phone(phone_number: str) -> str: #methode pour formater le numero de telephone entrer par le user en format congolais
    # 1. On ne garde que les chiffres
    digits = "".join(filter(str.isdigit, phone_number))
    
    # 2. Si ça commence par 0, on enlève le 0 et on met 243 (ex: 081... -> 24381...)
    if digits.startswith("0") and len(digits) == 10:
        return "243" + digits[1:]
        
    # 3. Si l'utilisateur a tapé directement 81... sans le 0 ni le 243 (9 chiffres)
    if len(digits) == 9 and not digits.startswith("243"):
        return "243" + digits
        
    # 4. Si c'est déjà au format 243... (12 chiffres)
    if digits.startswith("243") and len(digits) == 12:
        return digits
        
    # Renvoie le résultat nettoyé, ou le brut si le format est inconnu
    return digits


@Root.get("/guest_list/{event_id}",name="guest_list") #get the guest list
async def get_guest_list(request:Request,event_id:str,access_token = Cookie(None),db:AsyncSession = Depends(connecting),user = Depends(permission_required("view_guest"))):
    current_res = jwt.decode(access_token,secret,algorithms = [algo])
    user_id = current_res.get("user")
    if user_id:
        user_res = await db.execute(select(User).where(User.id ==user_id))
        user = user_res.scalars().first()
        for role in user.roles:
             user_role = role.name
    get_event_guest = select(Event).options(selectinload(Event.guests)).where(Event.id == event_id)#prendre l'evenement qui a des invites
    result = await db.execute(get_event_guest)
    event = result.scalars().first()
    guest_res = await db.execute(select(Guest).where(Guest.event_id==event_id).options(selectinload(Guest.invite)).order_by(desc(Guest.created_date)))#prendre les invites de l'evenement
    guests = guest_res.scalars().all()
    get_invite = await db.execute(select(Invite))
    invite = get_invite.scalars().all()
    get_present = select(Guest).where(Guest.event_id == event_id,Guest.is_present == True)
    get_absent = select(Guest).where(Guest.event_id == event_id,Guest.is_present == False)
    present_res = await db.execute(get_present) 
    absent_res = await db.execute(get_absent) 
    get_present_guest = present_res.scalars().all()#guest nombre qui sont present 
    get_absent_guest = absent_res.scalars().all()#guest nombre qui sont absent
    present_guest = len(get_present_guest)
    absent_guest = len(get_absent_guest)
    ticket_res = await db.execute(select(Ticket).where(Ticket.event_id == event_id))
    tickets = ticket_res.scalars().all()
    nb_sent_message = (await db.execute(select(func.count()).select_from(Guest).where(Guest.whatsapp_status == "sent"))).scalar() or 0 # nombre de message envoyer
    nb_failed_message = (await db.execute(select(func.count()).select_from(Guest).where(Guest.whatsapp_status == "failed"))).scalar() or 0 # nombre de message echoue
    nb_no_whatsapp_message = (await db.execute(select(func.count()).select_from(Guest).where(Guest.whatsapp_status == "no_whatsapp"))).scalar() or 0 # nombre de compte sans whatsapp
    nb_pending_message = (await db.execute(select(func.count()).select_from(Guest).where(Guest.whatsapp_status == "pending"))).scalar() or 0 # nombre de message en attende    
    #variable contenant message whatsapp
    sent_message = request.session.pop("sent_message",None)
    if not event :
        raise HTTPException(404,"aucun evenement trouvé")
    if not guests :
        return templates.TemplateResponse("Guest/List/notFound.html",{'request':request,"Error":'404','event':event})
    return templates.TemplateResponse("Guest/List/list.html",{'request':request,'sent_message':sent_message,'invite':invite,'event':event,'guests':guests,'event_id':event_id,'present_guest':present_guest,'absent_guest':absent_guest,'current_user_role':user_role,'tickets':tickets,
    'nb_sent_message':nb_sent_message,'nb_failed_message':nb_failed_message, 'nb_no_whatsapp_message':nb_no_whatsapp_message, 'nb_pending_message':nb_pending_message},status_code=303)

VERSION = "v20.0"

URL_MESSAGES = f"https://graph.facebook.com/{VERSION}/{whatsap_phone_Number_ID}/messages" # point d'access meta pour envoyer les message text
URL_MEDIA = f"https://graph.facebook.com/{VERSION}/{whatsap_phone_Number_ID}/media"# point d'access meta pour envoyer les images (medias)
twilio_client = Client(account_sid, auth_token)
#=============================send invite with twilio
class InvitationRequest(BaseModel):
    phone_number: str  # Format: +243XXXXXXXXX
    guest_name: str
    event_name: str
    invitation_code: str # Code unique pour le lien


@Root.post("/share_invite/{event_id}/{guest_id}")
async def send_whatsapp_ticket_api(
    request: Request,
    event_id: str, 
    guest_id: str, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupérer l'invité et l'événement en BDD
    guest_res = await db.execute(select(Guest).where(Guest.id == guest_id, Guest.event_id == event_id))
    guest = guest_res.scalars().first()
    
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    
    if not event or not guest:
        raise HTTPException(status_code=404, detail="Invité ou événement non trouvé")
        
    guest_name_backup = guest.name

    # 2. Nettoyage et validation du numéro de téléphone
    try:
        clean_phone = clean_and_format_rdc_phone(guest.telephone)
    except Exception:
        clean_phone = None

    if not clean_phone or len(clean_phone) != 12:
        request.session["flash_message"] = f"Le numéro de téléphone de {guest_name_backup} est invalide ou mal formaté."
        request.session["flash_type"] = "danger"
        return RedirectResponse(f"/guest_list/{event_id}", status_code=303)

    # 3. Préparation des variables du Template (Doit correspondre exactement à l'ordre du modèle {{1}} à {{8}})
    if getattr(guest, 'guest_type', '').lower() == 'couple':
        salutation_name = f"couple {guest.name}"
    else:
        salutation_name = guest.name

    invite_url = f"https://www.easyevent-rdc.com/invite/{event_id}/{guest_id}/create"
    
    # 1. Le dictionnaire de variables RESTE PUR (uniquement de 1 à 8)
    template_variables = {
        "1": str(salutation_name),
        "2": str(event.couple_name),
        "3": str(event.type),
        "4": str(get_day(event.date)),
        "5": f"{event.date.day}-{get_month(event.date)}-{event.date.year}",
        "6": str(event.date.time()),
        "7": str(guest.get_pass),
        "8": str(invite_url)
    }

    # 2. Configuration de base des arguments Twilio
    twilio_kwargs = {
        "from_": twilio_number,
        "to": f"whatsapp:+{clean_phone}",
        "content_variables": json.dumps(template_variables)
    }

# 3. L'aiguillage propre pour le SID et le paramètre média séparé
    if event.photo_url:
        twilio_kwargs["content_sid"] = media_content
        # Pour le template média, l'image se passe dans 'media_url' et non dans 'content_variables'
        twilio_kwargs["media_url"] = [event.photo_url]
    else:
        twilio_kwargs["content_sid"] = text_content
        # Pour le template texte, pas de media_url, tout reste vide d'image
   

    # 5. Envoi unitaire non bloquant
    try:
        message = await asyncio.to_thread(
            twilio_client.messages.create, 
            **twilio_kwargs
        )
        
        # 🟢 SUCCÈS : Commiter le changement de statut et message flash positif
        guest.whatsapp_status = "sent"
        await db.commit()
        
        request.session["flash_message"] = f"Invitation envoyée officiellement à {guest_name_backup} !"
        request.session["flash_type"] = "success"

    except TwilioRestException as err:
        await db.rollback()
        
        # Gestion intelligente de l'état si le numéro n'a pas WhatsApp
        if err.code == 63024 or "not a valid whatsapp" in err.msg.lower():
            guest.whatsapp_status = "no_whatsapp"
            request.session["flash_message"] = f"Le numéro de {guest_name_backup} n’a pas de compte WhatsApp."
            request.session["flash_type"] = "warning"
        else:
            guest.whatsapp_status = "failed"
            request.session["flash_message"] = f"Échec Twilio (Code {err.code}) : {err.msg}"
            request.session["flash_type"] = "danger"
        
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        request.session["flash_message"] = f"Erreur système lors de l'envoi : {str(e)}"
        request.session["flash_type"] = "danger"

    # Redirection propre vers la liste des invités
    return RedirectResponse(f"/guest_list/{event_id}", status_code=303)
#===============================================
class TicketRequest(BaseModel):
    to_phone: str          # Exemple: "243897401210"
    guest_name: str        # Nom de l'invité
    ticket_code: str       # Code unique du billet (ex: "INV-2026-XYZ")

@Root.post("/whatsapp/share_invite/{event_id}/{guest_id}")
async def send_whatsapp_ticket_api(
    request: Request,
    event_id: str, 
    guest_id: str, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupérer l'invité et l'événement en BDD
    guest_res = await db.execute(select(Guest).where(Guest.id == guest_id, Guest.event_id == event_id))
    guest = guest_res.scalars().first()
    
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    
    if not event or not guest:
        raise HTTPException(status_code=404, detail="Invité ou événement non trouvé")
        
    guest_name = guest.name

    # 2. Utilisation de ton système de nettoyage standardisé
    try:
        clean_phone = clean_and_format_rdc_phone(guest.telephone)
    except Exception:
        clean_phone = None

    if not clean_phone or len(clean_phone) != 12:
        request.session["flash_message"] = f"Le numéro de téléphone de {guest_name} est invalide ou mal formaté."
        request.session["flash_type"] = "danger"
        return RedirectResponse(f"/guest_list/{event_id}", status_code=303)

    # 3. Préparer les données et le texte d'accompagnement
    guest_get_pass = guest.get_pass
    invite_url = f"https://www.easyevent-rdc.com/invite/{event_id}/{guest_id}/create"
    # Gestion de la salutation personnalisée
    if getattr(guest, 'guest_type', '').lower() == 'couple':
        salutation = f"Bonjour très cher couple {guest_name},"
    else:
        salutation = f"Bonjour très cher {guest_name},"
    message = (
        f"🚨 *INVITATION OFFICIELLE (EasyInvite)* 🚨\n\n"
        f"Bonjour très cher(e) {salutation},\n\n"
        f"Nous, couple {event.couple_name}, avons l'honneur de vous inviter à notre événement de *{event.type}*, "
        f"qui se tiendra en date du {get_day(event.date)} le {event.date.day}-{get_month(event.date)}-{event.date.year} "
        f"à partir de {event.date.time()}.\n\n"
        f"🎫 *Votre jeton d'accès à la salle :* {guest_get_pass}\nCe jeton peut être utilisé en cas de manque du QR Code disponible sur le lien ci-dessous :\n\n"
        f"🔗 Cliquez ici pour voir l'invitation et ses détails : {invite_url}\n\n"
        f"📌 *Veuillez présenter le QR Code disponible sur le lien ci-dessus à l'entrée.*"
    )
    
    headers_msg = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json"
    }

    media_id = None

    # Ouverture du client HTTP asynchrone
    async with httpx.AsyncClient() as client:
        
        # Traitement de l'image (Optionnel - Fallback transparent vers texte seul en cas d'erreur)
        if event.photo_url:
            try:
                image_response = await client.get(event.photo_url, timeout=5.0)
                if image_response.status_code == 200:
                    headers_media = {"Authorization": f"Bearer {whatsapp_token}"}
                    data_media = {'messaging_product': 'whatsapp'}
                    files = {'file': ('wedding_photo.png', image_response.content, 'image/png')}
                    
                    media_response = await client.post(
                        URL_MEDIA, 
                        headers=headers_media, 
                        data=data_media, 
                        files=files, 
                        timeout=8.0
                    )
                    if media_response.status_code == 200:
                        media_id = media_response.json().get("id")
            except Exception as e:
                print(f"⚠️ Impossible de traiter la photo ({str(e)}), envoi en mode texte seul.")

        # Construction du payload Meta
        if media_id:
            data_msg = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "image",
                "image": {"id": media_id, "caption": message}
            }
        else:
            data_msg = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_phone,
                "type": "text",
                "text": {"preview_url": False, "body": message}
            }
        
        # Envoi final à l'API Meta
        try:
            meta_response = await client.post(URL_MESSAGES, headers=headers_msg, json=data_msg, timeout=15.0)
            meta_response.raise_for_status() 
            
            # 🟢 SUCCÈS : Mise à jour BDD et message flash positif
            guest.whatsapp_status = "sent"
            await db.commit()
            
            request.session["flash_message"] = f"Invitation envoyée avec succès à {guest_name} !"
            request.session["flash_type"] = "success"

        except httpx.HTTPStatusError as err:
            await db.rollback()
            try:
                error_data = err.response.json()
                error_msg = error_data.get("error", {}).get("message", "Erreur Meta")
                error_code = error_data.get("error", {}).get("code")
            except Exception:
                error_msg = err.response.text.lower()
                error_code = None
            
            # Analyse de l'erreur Meta pour adapter le statut en base de données
            if error_code == 131030 or "not a whatsapp account" in error_msg:
                guest.whatsapp_status = "no_whatsapp"
                request.session["flash_message"] = f"Le numéro de {guest_name} n'est pas associé à un compte WhatsApp."
                request.session["flash_type"] = "warning"
            else:
                guest.whatsapp_status = "failed"
                request.session["flash_message"] = f"Échec de l'envoi de l'invitation : {error_msg}"
                request.session["flash_type"] = "danger"
            
            await db.commit()
            
        except Exception as e:
            # Erreur de connexion ou coupure réseau locale
            await db.rollback()
            request.session["flash_message"] = f"Erreur réseau lors de la communication avec Meta : {str(e)}"
            request.session["flash_type"] = "danger"

    # Redirection unique et propre dans 100% des scénarios vers la liste des invités
    return RedirectResponse(f"/guest_list/{event_id}", status_code=303)
#---------------------------------------
@Root.post("/share_all_invites/{event_id}")
async def send_all_whatsapp_tickets_api(
    request: Request,
    event_id: str, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérifier si l'événement existe
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    
    if not event:
        request.session["flash_message"] = "Événement non trouvé."
        request.session["flash_type"] = "danger"
        return RedirectResponse(f"/guest_list/{event_id}", status_code=303)
        
    # On récupère uniquement les IDs pour la tâche de fond
    guest_res = await db.execute(select(Guest.id).where(Guest.event_id == event_id))
    guest_ids = guest_res.scalars().all()
    
    if not guest_ids:
        request.session["flash_message"] = "Aucun invité trouvé pour cet événement."
        request.session["flash_type"] = "warning"
        return RedirectResponse(f"/guest_list/{event_id}", status_code=303)

    # 2. Lancer la distribution en arrière-plan
    background_tasks.add_task(process_bulk_sending, guest_ids, event_id)

    request.session["flash_message"] = f"La distribution de masse a été lancée via Twilio pour {len(guest_ids)} invités."
    request.session["flash_type"] = "success"
    return RedirectResponse(f"/guest_list/{event_id}", status_code=303)


# 3. Tâche de fond optimisée pour Twilio avec gestion des transactions isolées
async def process_bulk_sending(guest_ids: list[str], event_id: str):
    
    # --- ÉTAPE 1 : RÉCUPÉRATION DES INFOS DE L'ÉVÉNEMENT ---
    async with AsyncSessionLocal() as db_bg:
        event_res = await db_bg.execute(select(Event).where(Event.id == event_id))
        event = event_res.scalars().first()
        if not event:
            print("❌ Événement introuvable en tâche de fond.")
            return
        
        couple_name = event.couple_name
        event_type = event.type
        event_date = event.date
        photo_url = event.photo_url

    # --- ÉTAPE 2 : DISTRIBUTION DE MASSE AVEC TEMPLATE TWILIO ---
    for g_id in guest_ids:
        
        async with AsyncSessionLocal() as db_loop:
            guest_res = await db_loop.execute(select(Guest).where(Guest.id == g_id))
            guest = guest_res.scalars().first()
            if not guest:
                continue

            # Nettoyage et uniformisation du numéro de téléphone
            try:
                clean_phone = clean_and_format_rdc_phone(guest.telephone)
            except Exception:
                continue
            
            # Gestion de la salutation personnalisée (Variable {{1}})
            if getattr(guest, 'guest_type', '').lower() == 'couple':
                salutation_name = f"couple {guest.name}"
            else:
                salutation_name = guest.name

            invite_url = f"https://www.easyevent-rdc.com/invite/{event_id}/{guest.id}/create"
            
            # Ordre strict correspondant aux variables du Template Meta {{1}} à {{8}}
            template_variables = {
                "1": salutation_name,
                "2": couple_name,
                "3": event_type,
                "4": get_day(event_date),
                "5": f"{event_date.day}-{get_month(event_date)}-{event_date.year}",
                "6": str(event_date.time()),
                "7": guest.get_pass,
                "8": invite_url
            }

            # Configuration des arguments de l'API Twilio Content
            twilio_kwargs = {
                "from_": twilio_number,
                "to": f"whatsapp:+{clean_phone}",
                "content_sid": content_sid, #  Ton code Content SID (Approved) du template dans twilio
                "content_variables": json.dumps(template_variables) # Sérialisation obligatoire en JSON String
            }
            print(f"DEBUG TIMING - From: {twilio_number} | To: whatsapp:+{clean_phone}")
            # Si l'événement possède une image de couverture, Twilio la joint automatiquement
            if event.photo_url:
                twilio_kwargs["media_url"] = [event.photo_url]

            # --- ENVOI VIA THREAD NON-BLOQUANT ---
            try:
                message = await asyncio.to_thread(
                    twilio_client.messages.create, 
                    **twilio_kwargs
                )
                
                guest.whatsapp_status = "sent"
                await db_loop.commit()
                print(f"📩 Envoyé officiellement à {guest.name} (SID: {message.sid})")

            except TwilioRestException as err:
                await db_loop.rollback()
                new_status = "failed"
                
                # Code 63024 : Numéro introuvable sur le réseau WhatsApp
                if err.code == 63024 or "not a valid whatsapp" in err.msg.lower():
                    new_status = "no_whatsapp"
                
                guest.whatsapp_status = new_status
                await db_loop.commit()
                print(f"💥 Échec Twilio pour {guest.name} (Code: {err.code}, Statut: {new_status})")

            except Exception as e:
                await db_loop.rollback()
                guest.whatsapp_status = "failed"
                await db_loop.commit()
                print(f"❌ Erreur système pour {guest.name}: {e}")

            # Pause ultra-légère (Twilio gère les files d'attente intelligemment)
            await asyncio.sleep(0.2)

@Root.get("/sms_sharing_invite/{event_id}/{guest_id}")
async def send_whatsapp_redirect(event_id: str,guest_id: str, db: AsyncSession = Depends(connecting)):
    # 1. Récupérer l'invité en BDD
    guest_res = await db.execute(select(Guest).where(Guest.id == guest_id,Guest.event_id == event_id))
    guest = guest_res.scalars().first()
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    if not event or not guest:
        raise HTTPException(status_code=404, detail="evenement ou Invité non trouvé")
    # 2. Préparer les données
    guest_get_pass = guest.get_pass
    invite_url = f"http://easyinvite-1.onrender.com/invite/{event_id}/{guest_id}/create"
    message = f"INVITATION OFFICIELLE\n\nBonjour {guest.name}, nous avons l'honneur de vous inviter à notre événement de {event.type} qui se tiendra en date du {get_day(event.date)} le {event.date.day}-{get_month(event.date)}-{event.date.year} a partir de {event.date.time()}.\n\n voici votre jeton d'accès a la salle*{guest_get_pass}* "
    # 3. Nettoyer le numéro (ne garder que les chiffres)
    # On suppose que le numéro est stocké avec l'indicatif pays (ex: 243...)
    clean_phone = "".join(filter(str.isdigit, guest.telephone))
    # 4. Encoder le message pour l'URL
    encoded_message = urllib.parse.quote(message)
    sms_link = f"sms:{clean_phone}?body={encoded_message}"
    # 5. Rediriger l'utilisateur directement vers WhatsApp
    return RedirectResponse(url=sms_link)
    #---------

@Root.get("/telephone/{event_id}") #la rechecher d'une donnee
async def searchEvent(request:Request,event_id :str,telephone:str = None,db:AsyncSession = Depends(connecting),user = Depends(permission_required("view_guest"))):
    query =select(Guest).where(Guest.event_id==event_id)
    if telephone:
        searched_number = format_to_drc_phone(telephone)
        query =(select(Guest).where(Guest.telephone.ilike(f"%{searched_number}%"),Guest.event_id==event_id)\
        )#.order_by(asc(Event.created_date), desc(Event.created_date))\
    #)# .offset(offset)\
    #     .limit(per_page)) # rechercher la donnee renseigner dans la barre de recherche, ilike permet d'ignorer le magiscule ou miniscule
    res = await db.execute(query)
    guests =res.scalars().all()
    event_res = await db.execute(select(Event).where(Event.id==event_id))
    event =event_res.scalars().first()
    if not guests :
        raise HTTPException(404,"invite introuvable")
    return templates.TemplateResponse("Guest/List/list.html",{'request':request,"guests":guests,'event':event,'event_id':event_id})

@Root.get('/guest/{guest_id}/{event_id}/detail')#detail endpoint
async def guestDetail(request:Request,guest_id:str,event_id:str,user=Depends(permission_required("view_guest")),db:AsyncSession = Depends(connecting)):
    get_guest =select(Guest).where(Guest.id ==guest_id,Guest.event_id == event_id)
    result = await db.execute(get_guest)
    guest =result.scalars().first()
    if not guest :
        raise HTTPException(404,"invite non trouvé")
    return templates.TemplateResponse("Guest/List/detail.html",{'request':request,"guest":guest,"event_id":event_id},status_code=303)

#====================================creation et edition d'un guest

def clean_and_format_rdc_phone(phone_input: str) -> str: #methode de formatage du numero d'un guest
    if not phone_input:
        return ""
        
    # 1. On ne garde UNIQUEMENT les chiffres
    clean_phone = "".join(filter(str.isdigit, str(phone_input)))
    
    # 2. Si le numéro commence par "0", on remplace le "0" par "243" (ex: 0897401210 -> 243897401210)
    if clean_phone.startswith("0"):
        clean_phone = "243" + clean_phone[1:]
        
    # 3. Si l'utilisateur a écrit directement sans le 0 ni le 243 (ex: 897401210), on ajoute "243"
    elif len(clean_phone) == 9 and clean_phone.startswith(("8", "9", "7")) or clean_phone.startswith("6"):
        clean_phone = "243" + clean_phone
        
    return clean_phone

@Root.get("/create/{event_id}/guest", name="guestForm") #get the guest register form
async def get_invited(
    request: Request,
    event_id: str,
    success: int | None = None,
    db: AsyncSession = Depends(connecting),
    user: User = Depends(permission_required("create_guest"))
):
    # 1. Récupérer l'événement afin d'y associer l'invité
    select_event = select(Event).options(selectinload(Event.guests)).where(Event.id == event_id)
    result = await db.execute(select_event)
    event = result.scalars().first() 
    
    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    # 2. Extraire CORRECTEMENT les données stockées en session
    form_data = request.session.pop('form_data', {})
    # 3. Récupérer l'éventuel message d'erreur s'il existe
    uniqueValueError = form_data.get('uniqueValueError', None)
    get_success = success == 1
    csrf_token = secrets.token_urlsafe(32)
    response =  templates.TemplateResponse(
        "Guest/Forms/form.html",
        {
            'request': request,
            'event': event,
            'success': get_success,
            'uniqueValueError': uniqueValueError,
            'guestName': form_data.get('guestName', ''),
            'guestType': form_data.get('guestType', ''),
            'guestPlace': form_data.get('guestPlace', ''),
            'guestTel': form_data.get('guestTel', ''),
            'csrf_token':csrf_token
        }
    )
    response.set_cookie(
        key = "fastapi-csrf-token",
        value = csrf_token,
        httponly = True,
        secure = set_secure_cookie,
        samesite = "lax",
        path = "/"
    )
    return response

@Root.post('/create/{event_id}/guest')
async def newGuest(
    request: Request,
    event_id: str,
    guestName: str = Form(...),
    guestType: str = Form(None),
    guestPlace: str = Form(None),
    guestTel: str = Form(...),
    photo: UploadFile = File(None),
    csrf_token :str = Form(...),
    user = Depends(permission_required("create_guest")),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf),
):
    # 1. Vérifier si l'événement existe
    select_event = select(Event).where(Event.id == event_id)
    get_event = await db.execute(select_event)
    event = get_event.scalars().first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    # Fonction utilitaire locale pour stocker les données en session en cas d'erreur
    def set_data(message):
        request.session['form_data'] = {
            'uniqueValueError': message, 
            'guestName': guestName,
            'guestType': guestType,
            'guestPlace': guestPlace, 
            'guestTel': guestTel,
            'csrf_token': csrf_token
        }

    # 2. Nettoyer et formater le numéro entré
    formatted_tel = clean_and_format_rdc_phone(guestTel)
    
    # Validation du format RDC (243XXXXXXXXX)
    if len(formatted_tel) != 12 or not formatted_tel.startswith("243"):
        error_message = "Le numéro de téléphone est invalide. Exemple valide : 0897401210 ou +243897401210"
        return templates.TemplateResponse(
            "Guest/Forms/form.html", 
            {
                'request': request, 'guestName': guestName, 'guestType': guestType, 
                'guestTel': guestTel, 'guestPlace': guestPlace, 'event': event, 'csrf_token': csrf_token,
                'uniqueValueError': error_message  # On utilise 'uniqueValueError' pour rester cohérent avec le GET
            }, 
            status_code=400
        )

    # 3. Vérifier si ce numéro existe déjà pour cet événement
    select_guest_tel = select(Guest).where(and_(Guest.telephone == formatted_tel, Guest.event_id == event_id))
    tel_res = await db.execute(select_guest_tel)
    is_guest_tel = tel_res.scalars().first()
    
    if is_guest_tel:
        error_msg = 'Un invité existe déjà avec ce numéro de téléphone pour cet événement.'
        set_data(error_msg)
        return RedirectResponse(f'/create/{event_id}/guest', status_code=303)
                
    # 5. Création du Guest et de l'invitation liée
    guest_get_pass = str(uuid4())[:8]
    guest = Guest(
        name=guestName,
        guest_type=guestType,
        place=guestPlace,
        telephone=formatted_tel,  # Sauvegarde standardisée en BDD !
        event_id=event_id,
        qr_token=str(uuid4()),
        get_pass=guest_get_pass,
    ) 

    db.add(guest)
    await db.flush()  # Génère l'ID du guest pour la table Invite
    
    new_invite = Invite(
        qr_token=str(uuid4()),
        guest_id=guest.id
    )
    db.add(new_invite)
    
    try:
        await db.commit()
    except Exception:
        await db.rollback()     
        raise HTTPException(status_code=500, detail="Erreur lors de la sauvegarde en base de données.")   
    return RedirectResponse(url=f'/create/{event_id}/guest?success=1', status_code=303)

@Root.get("/edit_guest_form/{event_id}/{guest_id}")
async def editGuest(
    request: Request,
    event_id: str,
    guest_id: str,
    user = Depends(permission_required("edit_guest")),
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupérer le guest et l'événement
    get_guest = select(Guest).where(Guest.id == guest_id, Guest.event_id == event_id).options(selectinload(Guest.invite))
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalars().first()
    if not event or not guest:
        raise HTTPException(status_code=404, detail="Invité non trouvé")
    
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    csrf_token = secrets.token_urlsafe(32)
    # 2. Récupérer l'erreur flash éventuelle (renommée en uniqueValueError pour uniformiser)
    uniqueValueError = request.session.pop('uniqueValueError', None)
    
    response =  templates.TemplateResponse(
        "Guest/Forms/edit_form.html",
        {
            'request': request,
            "guest": guest,
            'event': event,
            'csrf_token':csrf_token,
            'uniqueValueError': uniqueValueError  # Variable unifiée
        },
        status_code=200  
    )
    response.set_cookie(
        key="fastapi-csrf-token",
        value = csrf_token,
        httponly = True,
        secure = set_secure_cookie,
        samesite = "lax",
        path = "/"
    )
    return response

@Root.post("/edit_guest_form/{event_id}")
async def editGuestPost(
    request: Request,
    event_id: str,
    guest_id: str = Form(...),
    guestName: str = Form(...),
    guestType: str = Form(...),
    guestPlace: str = Form(...),
    guestState: int = Form(...),
    guestTel: str = Form(),
    csrf_token : str = Form(...),
    photo: UploadFile = File(None),
    user = Depends(permission_required("edit_guest")),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    # 1. Récupérer l'invité et l'événement
    get_new_guest = select(Guest).where(Guest.id == guest_id, Guest.event_id == event_id).options(selectinload(Guest.invite))
    result = await db.execute(get_new_guest)
    guest = result.scalars().first()
    
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    
    if not guest or not event:
        raise HTTPException(status_code=404, detail="Invité ou événement non trouvé")
        
    # 2. Nettoyer et valider le numéro de téléphone au format 243
    formatted_tel = clean_and_format_rdc_phone(guestTel)
    
    if len(formatted_tel) != 12 or not formatted_tel.startswith("243"):
        error_message = "Le numéro de téléphone est invalide. Exemple : 0897401210"
        return templates.TemplateResponse(
            "Guest/Forms/edit_form.html", 
            {
                'request': request, 'guest': guest, 'guestName': guestName, 
                'guestType': guestType, 'guestTel': guestTel, 'guestPlace': guestPlace, 
                'guestState': guestState, 'event': event, 'uniqueValueError': error_message, 'csrf_token': csrf_token
            }, 
            status_code=400
        )
        
    # 3. Vérifier si le numéro existe déjà CHEZ UN AUTRE invité de cet événement
    select_guest_tel = select(Guest).where(and_(Guest.telephone == formatted_tel, Guest.event_id == event_id, Guest.id != guest_id))
    tel_res = await db.execute(select_guest_tel)
    is_guest_tel = tel_res.scalars().first()
    
    if is_guest_tel:
        error_message = 'Un invité existe déjà avec ce numéro de téléphone.'
        return templates.TemplateResponse(
            "Guest/Forms/edit_form.html", 
            {
                'request': request, 'guest': guest, 'guestName': guestName, 
                'guestType': guestType, 'guestTel': guestTel, 'guestPlace': guestPlace, 
                'guestState': guestState, 'event': event, 'uniqueValueError': error_message, 'csrf_token': csrf_token
            }, 
            status_code=400
        )

    # 4. Appliquer les modifications
    guest.name = guestName
    guest.guest_type = guestType
    guest.place = guestPlace
    guest.is_present = bool(guestState)
    guest.telephone = formatted_tel  #Sauvegarde du numéro standardisé
    
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return templates.TemplateResponse(
            'Guest/Forms/edit_form.html',
            {
                'request': request, 'event': event, 'guest': guest, 
                'guestName': guestName, 'guestType': guestType, 'guestPlace': guestPlace, 'guestTel': guestTel,
                'uniqueValueError': "Erreur d'intégrité de la base de données.", 'csrf_token': csrf_token
            },
            status_code=400
        )
    return RedirectResponse(f"/guest_list/{event_id}", status_code=303)

@Root.post('/delete_guest/{event_id}/guest')#root for deleting guest
async def deleteGuest(request:Request,event_id:str,guest_id:str=Form(...),user=Depends(permission_required("delete_guest")),db:AsyncSession=Depends(connecting)):
    get_guest_to_be_deleted = (select(Guest).where(Guest.id==guest_id,Guest.event_id == event_id).options(selectinload(Guest.invite)))
    result = await db.execute(get_guest_to_be_deleted)
    guest_to_be_deleted = result.scalars().first()
    if not guest_to_be_deleted: #si le guest n'existe pas dans l'evenement
        raise HTTPException(status_code = 404,detail="invité introuvable")
    await db.delete(guest_to_be_deleted)#suppresion du guest
    await db.commit()#application de modification dans la db
    return RedirectResponse(f"/guest_list/{event_id}",status_code=303)

