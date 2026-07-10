#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
import asyncio
import base64,qrcode,re
import os
from qrcode import QRCode
from fastapi import Request,Depends,APIRouter,HTTPException,Form,BackgroundTasks
from fastapi.responses import HTMLResponse,StreamingResponse,RedirectResponse,FileResponse
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
from utils.Qr_Utils.qrCodeUtils import generateInviteQrCode
from pathlib import Path
from playwright.sync_api import sync_playwright
from utils.cryptography.crypt_file import encrypt_token
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=3)
Root = APIRouter()
picture_dirs = Path("static/Pictures/{None}/")

templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
def get_event_deadline(event_date:datetime): #setting a deadline
    deadline = event_date - timedelta(days=2)
    return deadline

def generate_qr_code_base64(data: str) -> str:
    secure_id = encrypt_token(data) # On encrypte l'id de l'invité
    qr = QRCode(
        version=1,
        error_correction = qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4
    )
    qr.add_data(secure_id)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    memory = io.BytesIO()
    img.save(memory, format="PNG")

    binary_data = memory.getvalue()
    
    # 2. On encode ces octets en texte Base64
    base64_data = base64.b64encode(binary_data).decode("utf-8")
    
    # 3. On retourne la chaîne directement exploitable par l'attribut src de la balise <img>
    return f"data:image/png;base64,{base64_data}"

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

@Root.get("/qr/{event_id}/{guest_id}")#pour l'image du qr_code sur l'invitation
async def get_qr_img(event_id:str,guest_id:str):
    qr_image = generateInviteQrCode(guest_id)
    return StreamingResponse(qr_image,media_type = "image/png") 

@Root.get('/invite/{event_id}/{guest_id}/create', response_class=HTMLResponse)
async def getGuestInvite(
    request: Request,
    event_id: str,
    guest_id: str,
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupération optimisée du guest, son invitation et l'événement associé
    query = (
        select(Guest)
        .where(Guest.id == guest_id, Guest.event_id == event_id)
        .options(selectinload(Guest.invite), selectinload(Guest.event))
    )
    result = await db.execute(query)
    guestInvite = result.scalars().first()
    
    # 2. Vérification d'existence (Sécurité)
    if not guestInvite or not guestInvite.event:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html", {"request": request})
        
    event = guestInvite.event
    invite = guestInvite.invite
    
    # 3. Génération du QR Code Base64 indispensable pour le template
    # (Met à jour le nom de ta fonction si nécessaire)
    qr_code_url = generateInviteQrCode(guest_id)
    
    # 4. Construction propre du lien Google Maps si l'adresse existe
    google_maps_url = None
    if event.address:
        safe_location = urllib.parse.quote(event.address)
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={safe_location}"
        
    # 5. Préparation des variables de contexte communes
    copyright_year = datetime.now()
    event_img = event.photo_url
    event_type = event.type
    
    context = {
        "request": request,
        "guest": guestInvite,
        "invite": invite,
        "event": event,
        "copyright": copyright_year,
        "event_img": event_img,
        "qr_code_url": qr_code_url,  # Ajout crucial ici
        "google_map": google_maps_url,
        "event_day": get_day(event.date) if event.date else "",
        "event_month": get_month(event.date) if event.date else ""
    }
    
    # 6. Routage dynamique vers les templates selon le type d'événement
    if event_type == "Mariage":
        if event.language == "en":
            return templates.TemplateResponse("Invitation/show_invite/wedding_event/en_wedding_event.html", context)
        return templates.TemplateResponse("Invitation/show_invite/wedding_event/wedding_event.html", context)
        
    elif event_type == "birth_day":
        return templates.TemplateResponse("Invitation/show_invite/birth_day_event/birthday_event.html", context)
        
    elif event_type == "conference":
        return templates.TemplateResponse("Invitation/show_invite/conference_event/conference_event.html", context)
        
    elif event_type == "other":
        return templates.TemplateResponse("Invitation/show_invite/other/ticket.html", context)
        
    # Au cas où le type d'événement ne correspond à rien de connu
    return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html", {"request": request})

@Root.get('/transfer_message',name="message")
async def show_transfer_message(request:Request):
    return templates.TemplateResponse("Invitation/show_invite/other/message.html",{'request':request})


@Root.get("/presence/confirmation/{guest_id}/{event_id}", response_class=HTMLResponse)
async def confirm_presence(request: Request, guest_id: str, event_id: str, db: AsyncSession = Depends(connecting)):
    # Récupération optimisée avec chargement des relations nécessaires
    get_guest = (
        select(Guest)
        .where(Guest.id == guest_id, Guest.event_id == event_id)
        .options(
            selectinload(Guest.invite).options(selectinload(Invite.guestResponse)),
            selectinload(Guest.event)
        )
    )
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    
    if not guest or not guest.event:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html", {'request': request})
        
    event = guest.event
    event_img = event.photo_url if event.photo_url else None
    
    # Récupération du message flash de la session (Erreur ou Succès)
    get_message = request.session.pop("message", None) 
    year = datetime.now().year
    
    context = {
        'request': request,
        "guest": guest,
        "event": event,
        'event_img': event_img,
        'message': get_message,
        "copyright": year
    }
    
    if event.language == "en":
        return templates.TemplateResponse("Invitation/show_invite/en_presence_confirmation.html", context)
    return templates.TemplateResponse("Invitation/show_invite/presence_confirmation.html", context)


@Root.post("/presence/confirmation/{guest_id}/{event_id}")
async def GuestResponse(
    request: Request,
    guest_id: str,
    event_id: str,
    response: str = Form(...),
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'existence du couple invité/événement
    get_guest = (
        select(Guest)
        .where(Guest.id == guest_id, Guest.event_id == event_id)
        .options(selectinload(Guest.event), selectinload(Guest.invite))
    )
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    
    if not guest or not guest.event:
        return templates.TemplateResponse("Invitation/show_invite/inviteNotFound.html", {'request': request})
        
    event = guest.event
    
    # 2. Sécurité : Vérification de la date limite
    # Utilisation d'un datetime naïf ou UTC selon comment get_event_deadline est codé.
    today = datetime.now() 
    deadline = get_event_deadline(event.date)
    
    if today > deadline:
        if event.language == "en":
            request.session['message'] = "❌ The deadline for confirmation has passed."
        else:
            request.session['message'] = "❌ La date limite pour la confirmation est dépassée."
        return RedirectResponse(f'/presence/confirmation/{guest_id}/{event_id}', status_code=303)
        
    # 3. Vérification si une réponse existe déjà
    get_response = select(PresenceConfirmation).where(PresenceConfirmation.guest_id == guest_id)
    response_result = await db.execute(get_response)
    exist_response = response_result.scalars().first()
    
    if exist_response:
        # Mise à jour de la réponse existante
        exist_response.invite_id = guest.invite.id
        exist_response.response = response
        exist_response.send_at = datetime.utcnow()
        
        message = "✅ Your response has been updated." if event.language == "en" else "✅ Votre réponse a été mise à jour."
    else: 
        # Création d'une nouvelle réponse
        presence = PresenceConfirmation(
            guest_id=guest_id,
            invite_id=guest.invite.id, 
            response=response
        )
        db.add(presence)
        message = "🎉 Your presence has been registered." if event.language == "en" else "🎉 Votre présence a été enregistrée."
        
    # 4. Commit sécurisé en base de données
    try:
        await db.commit()
        request.session['message'] = message  # On enregistre le succès UNIQUEMENT si le commit réussit
    except Exception as e:
        await db.rollback()
        # En production, loggez la vraie erreur 'e' sur le serveur, ne la montrez pas à l'utilisateur
        request.session['message'] = "❌ Une erreur technique est survenue. Veuillez réessayer."
        
    # 5. Redirection finale propre (Pattern PRG)
    return RedirectResponse(f'/presence/confirmation/{guest_id}/{event_id}', status_code=303)


# @Root.get("/invitation/download-image/{guest_id}")
# async def download_invitation_image(guest_id: str, db: AsyncSession = Depends(connecting)):
#     guest = (await db.execute(select(Guest).where(Guest.id == guest_id).options(selectinload(Guest.event)))).scalars().first()
#     if not guest:
#         raise HTTPException(status_code=404, detail="Invité non trouvé.")
        
#     guest_name = guest.name
#     event_date = guest.event.date if guest.event else None
#     event_location = guest.event.location if guest.event else None
#     qr_data = f"https://easyinvite.cd/verify/{guest_id}"
#     qr_code_generated = generate_qr_code_base64(qr_data)

#     guest_name_clean = guest_name.replace(' ', '_')
#     output_image = f"invitation_de_{guest_name_clean}.png"
    
#     try:
#         template = templates.get_template("Invitation/show_invite/wedding_event/invite.html")
#         html_content = template.render(
#             guest_name=guest_name,
#             couple_name=guest.event.couple_name if guest.event else None,
#             qr_code_url=qr_code_generated,
#             event_date=event_date,
#             event_location=event_location,
#             phone_number="+243 81 234 56 78",
#             event_image=guest.event.photo_url if guest.event else None,
#             get_pass = guest.get_pass
#         )
        
#         # Mode Asynchrone fonctionnel
#         async with async_playwright() as p:
#             browser = await p.chromium.launch(headless=True)
#             page = await browser.new_page()
            
#             await page.set_viewport_size({"width": 1200, "height": 500})
#             await page.set_content(html_content)
#             await page.wait_for_load_state("networkidle")
            
#             invitation_element = await page.query_selector(".invitation-container")
#             if not invitation_element:
#                 raise Exception("La classe '.invitation-container' n'a pas été trouvée.")
                
#             await invitation_element.screenshot(path=output_image)
#             await browser.close()
        
#         return FileResponse(
#             path=output_image,
#             filename=f"Invitation_{guest_name_clean}.png",
#             media_type="image/png"
#         )
        
#     except Exception as e:
#         import traceback
#         traceback.print_exc()
#         raise HTTPException(status_code=500, detail=f"Erreur de génération : {str(e)}")

executor = ThreadPoolExecutor(max_workers=3)

# La fonction de génération PDF isolée et synchrone
def _generate_pdf_worker(html_content: str, output_pdf_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Injection immédiate du HTML
        page.set_content(html_content, wait_until="commit")
        
        # Petit délai de sécurité de 4s max pour charger les images de Cloudinary
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            print("Note: Temps d'attente réseau dépassé, génération du PDF lancée.")
            
        # Génération du PDF avec les dimensions de votre choix
        page.pdf(
            path=output_pdf_path,
            width="1200px",
            height="600px",
            print_background=True  # Garde l'image Cloudinary en arrière-plan
        )
        browser.close()
def remove_file(path: str):#supprime le fichier temporaire apres telechargement 
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception as e:
        print(f"Erreur lors de la suppression du fichier temporaire : {e}")

@Root.get("/invitation/download-pdf/{guest_id}")
async def download_invitation_pdf(
    guest_id: str,
    background_tasks: BackgroundTasks, 
    request: Request,  # Ajouté pour générer l'URL dynamique du QR Code
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupération de l'invité et de l'événement
    query = select(Guest).where(Guest.id == guest_id).options(selectinload(Guest.event))
    result = await db.execute(query)
    guest = result.scalars().first()
    
    if not guest:
        raise HTTPException(status_code=404, detail="Invité non trouvé.")
    if not guest.event:
        raise HTTPException(status_code=404, detail="Événement associé non trouvé.")
        
    event = guest.event
    
    # 2. Sécurisation du nom de fichier sur le serveur (On utilise l'UUID de l'invité)
    output_pdf = f"invitation_tmp_{guest_id}.pdf"
    
    # Nettoyage cosmétique du nom pour le fichier téléchargé par l'utilisateur
    # On retire tout caractère bizarre pour le nom final du téléchargement
    guest_name_clean = re.sub(r'[^\w\-_]', '_', guest.name)
    download_filename = f"Invitation_de_{guest_name_clean}.pdf"
    
    # 3. Génération dynamique du lien de vérification du QR Code
    # request.base_url s'adapte automatiquement (localhost en dev, easyinvite.cd en prod)
    qr_data = f"{str(request.base_url).rstrip('/')}/verify/{guest_id}"
    qr_code_generated = generate_qr_code_base64(qr_data)
    
    try:
        # 4. Préparation du template HTML avec les données réelles de la BDD
        template = templates.get_template("Invitation/show_invite/wedding_event/invite.html")
        html_content = template.render(
            guest_name=guest.name,
            couple_name=event.couple_name,
            qr_code_url=qr_code_generated,
            event_date=event.date,
            event_location=event.location,
            phone_number=event.contact_phone if hasattr(event, 'contact_phone') else "+243812345678", # À adapter selon ton modèle
            get_pass=guest.get_pass,
            event_image=event.photo_url
        )
        
        # 5. Exécution sécurisée dans le Thread Pool (Anti-NotImplementedError sous Windows)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(executor, _generate_pdf_worker, html_content, output_pdf)
        
        # 6. Planification de la suppression sécurisée après envoi
        background_tasks.add_task(remove_file, output_pdf)
        
        # 7. Retour du fichier vers le dossier "Téléchargements" de l'utilisateur
        return FileResponse(
            path=output_pdf,
            filename=download_filename,
            media_type="application/pdf"
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        # En production, on évite de renvoyer l'erreur technique brute à l'utilisateur
        raise HTTPException(status_code=500, detail="Une erreur est survenue lors de la génération de votre invitation PDF.")

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
    buffer = generateInviteQrCode(guest_id)
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



#-----------------------------------Ticket template------------------------------
@Root.get('/ticket/view/{event_id}/{ticket_id}')#endpoint pour le billet
async def get_ticket(request:Request,event_id:str,ticket_id:str ,db:AsyncSession = Depends(connecting)):
    res =  await db.execute(select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.events),selectinload(Ticket.orders)))
    ticket = res.scalars().first()
    if not ticket  :
        raise HTTPException(status_code = 404,detail="event ou ticket introuvable")
    copyright = datetime.now()
    ticket_number = f"{ticket.number:03d}"
    return templates.TemplateResponse("Invitation/show_invite/other/ticket.html",{'request':request,'ticket':ticket,'ticket_number':ticket_number,'event_day':get_day(ticket.events.date),'copyright':copyright})
