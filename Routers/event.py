#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from asyncio.log import logger
from email.header import Header
import re

from fastapi import Request,Form,Depends,HTTPException,APIRouter,UploadFile,File,Cookie,status
from fastapi.responses import RedirectResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from uuid import uuid4
import os,cloudinary,cloudinary.uploader,secrets
from db_setting import engine,connecting
import models
import models
import schemas
from sqlalchemy.orm import selectinload
from sqlalchemy import func,desc,select
from sqlalchemy.ext.asyncio import AsyncSession
from models import *
from jose import jwt
from typing import Optional
from datetime import datetime
from openpyxl import Workbook
from io import BytesIO
from Routers.loging import get_current_user_from_cookie
from app.security.permissions import permission_required,has_permission
from config import secret,algo,set_secure_cookie,verify_csrf
from urllib.parse import quote

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static
Pictures = "static/Pictures/{None}"
#os.makedirs("Pictures",exist_ok=True)

from slowapi import Limiter
from slowapi.util import get_remote_address

# Initialisation du Rate Limiter pour les formulaires (ex: max 20 créations/min par IP)
limiter = Limiter(key_func=get_remote_address)

Cloud_name = os.getenv("CLOUD_NAME")
Cloud_api_key = os.getenv("CLOUD_API_KEY")
Cloud_api_secret = os.getenv("CLOUD_API_SECRET")
cloudinary.config(
    cloud_name = Cloud_name,
    api_key = Cloud_api_key,    
    api_secret  = Cloud_api_secret,
    secure = True
)
@Root.get("/research_event")
async def searchEvent(request:Request,researched_event:str,db:AsyncSession = Depends(connecting),user = Depends(permission_required("view_event"))):
    get_event =(select(Event).where(Event.name.like(f"%{researched_event}%")).options(selectinload(Event.guests)))
    result = await db.execute(get_event)
    event = result.scalars().all()
    if not event :
        eventNotFound = "aucun evenement trouvé a ce nom" #message a afficher si l'evenement n'est pas trouve
        return templates.TemplateResponse("Event/List/list_event.html",{'request':request,'eventNotFound':eventNotFound,'event':event})
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":event})

@Root.get("/event_list/",name="event_list")#get the event list 
async def getEventList(request:Request,  db:AsyncSession = Depends(connecting),access_token = Cookie(None)):
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles),selectinload(User.groups)))
    user = user_res.scalars().first()
    if user :

        for role in user.roles:
            user_role = role.name
        for user_group in user.groups:
            group_id = user_group.id
        if user_role == "admin":
            get_event =await db.execute(select(Event).options(selectinload(Event.guests)).order_by(desc(Event.created_date)))
            events = get_event.scalars().all()
            return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":events,'curent_user_role':user_role})
    get_event =await db.execute(select(Event).where(Event.group_id == group_id).options(selectinload(Event.guests),selectinload(Event.tickets)).order_by(desc(Event.created_date)))
    events = get_event.scalars().all()
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":events,'curent_user_role':user_role})

@Root.get("/event_description/{event_id}",name="main_event")#get the mainEventView
async def getEventForm(request:Request,event_id :str,
                       page:int = 1,
                       access_token=Cookie(None),
                       db:AsyncSession = Depends(connecting),user = Depends(permission_required("view_event"))):
    current_res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = current_res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles),selectinload(User.groups)))
    user = user_res.scalars().first()
    for role in user.roles:
        user_role = role.name
    select_event =(select(Event).where(Event.id==event_id).options(selectinload(Event.guests)))
    get_guests = await db.execute(select_event)
    event = get_guests.scalars().first()
    total =len(event.guests)
    #-----------------------pagination
    total_ticket = (await db.execute(select(func.count()).select_from(Ticket).where(Ticket.event_id == event_id))).scalar() or 0
    per_page = 50 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_pages = (total_ticket + per_page - 1) // per_page #le nombre total de page
    #total__guest_pages = (await db.execute(select(func.count()).select_from(Guest).where(Guest.event_id == event_id))).scalar() or 0
    stmt = (
    select(Ticket)
    .where(Ticket.event_id == event_id)
    .order_by(desc(Ticket.creation))  # Ferme la parenthèse de desc() ET de order_by() ici
    .offset(offset)
    .limit(per_page)
    .options(selectinload(Ticket.orders)) # Vérifie si c'est 'order' ou 'orders' dans ton modèle
)
    ticket_res = await db.execute(stmt)
    tickets = ticket_res.scalars().all()
    return templates.TemplateResponse("Event/Home/mainEventView.html",{'request':request,
    "tickets":tickets,"event":event,"total":total,'current_user_role':user_role,'total_pages': total_pages, 'page': page,})

@Root.get("/detail/event/{event_id}")#la root pour voir les detail d'un event
async def eventDetail(request:Request,event_id : str,access_token = Cookie(None),db:AsyncSession = Depends(connecting),user = Depends(permission_required("view_event"))):
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles),selectinload(User.groups)))
    user = user_res.scalars().first()
    for role in user.roles:
        user_role = role.name
    get_Event = await db.execute(select(Event).where(Event.id == event_id))
    event = get_Event.scalars().first()
    return templates.TemplateResponse("Event/List/detail.html",{'request':request,"event":event,'curent_user_role':user_role})

@Root.get("/event_form",name="event_form")#lq route renvoyant le formuliare de creation d'un evenment
def getEventForm(request:Request,user=Depends(permission_required("create_event"))):
    success_message = request.session.get("success")
    csrf_token = secrets.token_urlsafe(32)
    event_error = request.session.pop('event_error',None)
    session_form_data = request.session.pop('form_data',None)
    if session_form_data is None :
        form_data = {
            "errors":{"error":event_error},
            "fields":{},
            "system": {},
        }
    else : 
        form_data = session_form_data #les donnees renvoyeé la premiere fois qui doivent preremplire les champs
        if event_error:
            form_data["errors"]["error"] = event_error

    response =  templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"csrf_token":csrf_token, "creation_success": success_message,"data":form_data})
    response.set_cookie(
        key = "fastapi-csrf-token",
        value = csrf_token,
        httponly = True,
        samesite = "lax",
        secure = set_secure_cookie,
        path = "/"
    )
    return response

#------------------------------------------l'addresse du dossier de stockage des image
FOLDER_MAPPING = {
    "Mariage": "EasyInvite/wedding_events",
    "birth_day": "EasyInvite/birth_day_events",
    "conference": "EasyInvite/conference_events",
    "concours": "EasyInvite/concours_events"
}
DEFAULT_FOLDER = "EasyInvite/ticket_pictures"
#------------------------------------------


@Root.post("/create_event") #create an event
async def creatEvent(
    request: Request,
    eventName: str = Form(...),
    eventType: str = Form(...), 
    eventDate: datetime = Form(...),
    eventAddress: str = Form(),
    eventDescription: Optional[str] = Form(None),
    location: str = Form(...),
    photo: UploadFile = File(None),
    user = Depends(permission_required("create_event")),
    couple_name: str = Form(None),
    couple_phone_number: str = Form(...),
    access_token = Cookie(None),
    is_gift_active: bool = Form(None), #le cadeau
    language: str = Form(...), #la langue
    organizer: str = Form(None), #organisateur
    greetings: str = Form(None), #message de bienvenu
    total_place: int = Form(None), #espace d'accueil ou le nombre de place prevu
    is_featured: bool = Form(None), #l'event est a la une?
    city: str = Form(None), #la ville
    Db: AsyncSession = Depends(connecting),
    csrf_token: str = Form(...),
    _ = Depends(verify_csrf)
):
    res = jwt.decode(access_token, secret, algorithms=[algo])
    user_id = res.get("user")
    user_res = await Db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.groups), selectinload(User.roles))
    )
    user = user_res.scalars().first()
    group_id = None
    user_role = None #le role de l'utilisateur sera none par defaut pour eviter les erreurs
    is_event_photo = False
    photo_url, photo_public_id = None, None

    # 💾 Construction du dictionnaire de données (Sécurisé pour la session JSON)
    form_data = {
        "errors": {
            "error": "",
        },
        "fields": {
            "event_name": eventName.strip() if eventName else "",
            "event_type": eventType if eventType else "",
            "event_organizer": organizer if organizer else "",
            "language": language if language else "",
            "total_place": total_place if total_place else "",
            "couple_name": couple_name.strip() if couple_name else "",
            "couple_phone_number": couple_phone_number.strip() if couple_phone_number else "",
            "event_date": eventDate.isoformat() if eventDate else "",  # On transforme l'objet datetime en chaîne de caractères (ISO)
            "event_address": eventAddress.strip() if eventAddress else "",
            "location": location.strip() if location else "",
            "greetings": greetings if greetings else "",
            "event_description": eventDescription.strip() if eventDescription else "",
            "is_gift_active": bool(is_gift_active), 
            "is_featured": bool(is_featured), 
            "city": city if city else ""
        },
        "system": {
            "csrf_token": csrf_token,
            "organizer": organizer
        }
    }

    max_length = {
        "event_name": 50,
        "event_address" : 100,
        "event_location" : 50,
        "couple_name" :  50,
        "couple_phone_number": 15,
        "event_organizer" :  255,
        "event_photo_url": 255
    }

    if user.groups:
        group_id = user.groups[0].id if user.groups else None
        user_role = user.roles[0].name if user.roles else None

    # 1. Validation de la date
    if eventDate < datetime.now():
        request.session['event_error'] = "Entrez une date supérieure à la date actuelle ou entrez une date correcte !!!"
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    # 2. Validation du type de fichier
    if photo and photo.filename:
        if not photo.content_type or not photo.content_type.startswith("image/"):
            # Si erreur directe sans redirection, on passe form_data directement au template
            return templates.TemplateResponse(
                "Event/Forms/event_form.html",
                {
                    'request': request,
                    "img_error": 'Le fichier doit être une image !!!',
                    'form_data': form_data,
                    "csrf_token": csrf_token
                },
                status_code=400
            )

    # 3. Validations des longueurs (Sécurité BDD)
    if len(eventName) > max_length["event_name"]:
        request.session['event_error'] = f"Le nom de l'événement est trop long ({max_length['event_name']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    if len(eventAddress) > max_length["event_address"]:
        request.session['event_error'] = f"L'adresse est trop longue ({max_length['event_address']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    if len(location) > max_length["event_location"]:
        request.session['event_error'] = f"Le nom de la localisation est trop long ({max_length['event_location']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    #  CORRECTION ICI : On utilise la variable "organizer" (en minuscule)
    if organizer and len(organizer) > max_length["event_organizer"]:
        request.session['event_error'] = f"Le nom de l'organisateur est trop long ({max_length['event_organizer']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    if couple_name and len(couple_name) > max_length["couple_name"]:
        request.session['event_error'] = f"Le nom du couple est trop long ({max_length['couple_name']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)
    if couple_phone_number and len(couple_phone_number) > max_length["couple_phone_number"]:
        request.session['event_error'] = f"Le numéro de téléphone  est trop long ({max_length['couple_phone_number']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    #  CORRECTION ICI : On vérifie la longueur du nom de fichier (.filename) et non de l'objet UploadFile
    if photo and photo.filename and len(photo.filename) > max_length["event_photo_url"]:
        request.session['event_error'] = f"Le nom de l'image est trop long ({max_length['event_photo_url']} caractères max)."
        request.session['form_data'] = form_data
        return RedirectResponse("/event_form", status_code=303)

    # 4. Upload Cloudinary
    try:
        if photo and photo.filename:
            target_folder = FOLDER_MAPPING.get(eventType, DEFAULT_FOLDER)
            upload_result = await run_in_threadpool(
                cloudinary.uploader.upload, photo.file, folder=target_folder,
                transformation=[{'width': 1000, 'height': 1000, 'crop': 'limit'}, {'quality': "auto"}]
            )
            photo_url = upload_result['secure_url']
            photo_public_id = upload_result['public_id']
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors du chargement de l'image: {str(e)}")

    # 5. Enregistrement en Base de données
    try:
        newEvent = Event(
            name=eventName,
            type=eventType,
            date=eventDate,  # Ici, on passe bien l'objet datetime à SQLAlchemy
            address=eventAddress,
            description=eventDescription,
            location=location,
            couple_name=couple_name,
            couple_phone_number=couple_phone_number,
            created_by=user_id,
            guest_present=is_gift_active if is_gift_active else None,
            group_id=group_id,
            photo_url=photo_url if photo_url else None,
            photo_public_id=photo_public_id if photo_public_id else None,
            language=language,
            organizer=organizer,
            greeting_message=greetings,
            total_capacity=total_place,
            is_featured=is_featured,
            city=city if city else None
        )
        Db.add(newEvent)
        await Db.commit()
        await Db.refresh(newEvent)
    except Exception as e:
        await Db.rollback()
        print(f"🚨 [DB ERROR] : {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la création de l'événement")

    # 6. Succès !
    request.session["success"] = "Événement créé avec succès !"
    return RedirectResponse("/event_form", status_code=303)

@Root.get("/edit_event/{event_id}")#la root pour la modification d'un evenement
async def editEvent(request:Request,event_id : str,user=Depends(permission_required("edit_event")),db:AsyncSession = Depends(connecting)):
    edit_Event = select(Event).where(Event.id == event_id)
    res = await db.execute(edit_Event)
    editEvent = res.scalars().first()
    success = request.session.pop("success",None)
    csrf_token = secrets.token_urlsafe(32)
    session_form_data = request.session.pop("form_data",None) #les donnees soumis dans les form qui seront renvoyee lors de l'erreur
    if not editEvent:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    if session_form_data is None:
        form_data = {
            "errors":{
           'event_name' : "",
            'event_date' : "",
            'event_address' : "",
            'event_location' : "",
            'event_organizer' : "",
            'couple_name' : "",
            'couple_phone_number' : "",
            },
            "fields":{},
            "system":{}
        }
    else:
        form_data = session_form_data
    response =  templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"csrf_token":csrf_token,"event":editEvent,"success":success,"data":form_data})
    response.set_cookie(
        key = "fastapi-csrf-token",
        value = csrf_token,
        httponly = True,
        secure = set_secure_cookie,
        samesite = "lax",
        path = "/"
    )
    return response

@Root.post("/edit_event/{event_id}")
async def editEvent(
    request: Request,
    event_id: str,
    access_token = Cookie(None),
    eventName: str = Form(...),
    coupleName: str = Form(...),
    couple_phone_number: str = Form(...),
    eventType: str = Form(...),
    eventDate: datetime = Form(...),
    eventAddress: str = Form(...),
    location: str = Form(...),
    eventDescription: Optional[str] = Form(None),
    eventState: str = Form(...),
    photo: UploadFile = File(None),
    is_gift_active: bool = Form(None),
    language: str = Form(...),
    organizer: str = Form(None),
    greetings: str = Form(None),
    total_place: int = Form(None),
    city: str = Form(...),
    is_featured: bool = Form(None),
    db: AsyncSession = Depends(connecting),
    user = Depends(permission_required("edit_event")),
    csrf_token: str = Form(...),
    _ = Depends(verify_csrf)
):
    # 1. Récupération de l'événement en BDD
    res = await db.execute(select(Event).where(Event.id == event_id))
    editedEventData = res.scalars().first() 
    if not editedEventData:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    # 2. Récupération de l'utilisateur connecté
    res_jwt = jwt.decode(access_token, secret, algorithms=[algo])
    user_id = res_jwt.get("user")
    user_res = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.groups), selectinload(User.roles))
    )
    user = user_res.scalars().first()

    user_role = user.roles[0].name if user.roles else None

    # 3. Limites de caractères
    max_length = {
        "event_name": 50,
        "event_address" : 50,
        "event_location" : 50,
        "couple_name" :  50,
        "couple_phone_number": 15,
        "event_organizer" :  255,
        "event_photo_url": 255
    }

    # 4. Construction du dictionnaire de données et validation des erreurs
    form_data = {
        "errors": {
            "event_name": f"Le nom de l'événement est trop long ({max_length['event_name']} caractères max)." if len(eventName) > max_length["event_name"] else None,
            "event_date": "Entrez une date supérieure à la date actuelle ou entrez une date correcte !!!" if eventDate < datetime.now() else None,
            "event_address": f"L'adresse est trop longue ({max_length['event_address']} caractères max)." if len(eventAddress) > max_length["event_address"] else None,
            "event_location": f"Le nom de la localisation est trop long ({max_length['event_location']} caractères max)." if len(location) > max_length["event_location"] else None,
            "event_organizer": f"Le nom de l'organisateur est trop long ({max_length['event_organizer']} caractères max)." if organizer and len(organizer) > max_length["event_organizer"] else None,
            "couple_name": f"Le nom du couple est trop long ({max_length['couple_name']} caractères max)." if coupleName and len(coupleName) > max_length["couple_name"] else None,
            "couple_phone_number": f"Le numéro de téléphone  est trop long ({max_length['couple_phone_number']} caractères max)." if couple_phone_number and len(couple_phone_number) > max_length["couple_phone_number"] else None,

        },
        "fields": {
            "event_name": eventName,
            "couple_name": coupleName,
            "couple_phone_number": couple_phone_number,
            "event_type": eventType,
            "event_date": eventDate.isoformat() if eventDate else "",
            "event_address": eventAddress,
            "location": location,
            "event_description": eventDescription,
            "event_state": eventState,
            "is_gift_active": bool(is_gift_active),
            "language": language,
            "organizer": organizer,
            "greetings": greetings,
            "total_place": total_place,
            "is_featured": bool(is_featured),
            "city": city 
        }
    }

    # 5. Redirection si erreurs détectées
    if any(form_data["errors"].values()):
        request.session['form_data'] = form_data
        return RedirectResponse(f"/edit_event/{event_id}", status_code=303)

    # 6. Gestion du groupe de l'utilisateur (Non-admin)
    group_id = editedEventData.group_id
    groups = None
    if user_role != "admin":
        groups_res = await db.execute(select(Group).where(Group.id == group_id))
        groups = groups_res.scalars().first()

    # 7. Gestion de l'image (Cloudinary)
    photo_url = editedEventData.photo_url
    photo_public_id = editedEventData.photo_public_id
    
    if photo and photo.filename:
        # Sécurité format
        if not photo.content_type or not photo.content_type.startswith("image/"):
            request.session['form_data'] = form_data
            request.session['event_error'] = "Le fichier doit être une image !!!"
            return RedirectResponse(f"/edit_event/{event_id}", status_code=303)
            
        try:
            target_folder = FOLDER_MAPPING.get(eventType, DEFAULT_FOLDER)
            # Suppression de l'ancienne image si elle existe sur Cloudinary
            if photo_public_id:
                await run_in_threadpool(cloudinary.uploader.destroy, photo_public_id)
            
            # Upload de la nouvelle image
            upload_result = await run_in_threadpool(
                cloudinary.uploader.upload, photo.file, folder=target_folder,
                transformation=[{'width': 1000, 'height': 1000, 'crop': 'limit'}, {'quality': "auto"}]
            )
            photo_url = upload_result['secure_url']
            photo_public_id = upload_result['public_id']
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erreur lors du téléchargement de l'image: {str(e)}") 

    # 8. Mise à jour de l'objet SQLAlchemy
    editedEventData.name = eventName
    editedEventData.couple_name = coupleName
    editedEventData.couple_phone_number = couple_phone_number
    editedEventData.type = eventType
    editedEventData.date = eventDate
    editedEventData.address = eventAddress
    editedEventData.location = location
    editedEventData.description = eventDescription
    editedEventData.state = eventState
    editedEventData.guest_present = is_gift_active if is_gift_active else None
    editedEventData.photo_public_id = photo_public_id 
    editedEventData.photo_url = photo_url  
    editedEventData.organizer = organizer
    editedEventData.language = language
    editedEventData.greeting_message = greetings
    editedEventData.total_capacity = total_place
    editedEventData.is_featured = is_featured
    editedEventData.city = city if city else None

    # Gestion propre de la relation de groupe
    if user_role != "admin" and groups:
        editedEventData.groups = [groups]

    # 9. Commit sécurisé
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"🚨 [PROD DB ERROR] : {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la modification de l'événement")

    request.session["success"] = "🎉 Événement modifié avec succès !"
    return RedirectResponse("/event_list", status_code=303)

@Root.post("/delete_event/{event_id}")
async def deleteEvent(
    request: Request,
    event_id: str,
    user=Depends(permission_required("delete_event")),
    db: AsyncSession = Depends(connecting)
):
    # 1. On ne récupère l'événement QUE s'il n'est pas déjà soft-deleté
    event_query = select(Event).where(Event.id == event_id, Event.is_deleted == False)
    res = await db.execute(event_query)
    eventToDelete = res.scalars().first()
    
    if not eventToDelete:
        raise HTTPException(status_code=404, detail="Cet événement n'existe pas ou a déjà été supprimé")
    
    picture_to_be_deleted = eventToDelete.photo_public_id 
    is_wedding = eventToDelete.type.strip().lower() == "Mariage"
    
    try:
        if is_wedding:
            # --- HARD DELETE ---
            await db.delete(eventToDelete)
        else:
            # --- SOFT DELETE ---
            eventToDelete.is_deleted = True
            db.add(eventToDelete)

        # On valide d'abord la base de données de manière TRÈS stricte
        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, 
            detail=f"Erreur lors du traitement de la suppression en base de données : {str(e)}"
        )
        
    # 2. Une fois et UNIQUEMENT si le commit BDD a réussi, on nettoie Cloudinary
    if is_wedding and picture_to_be_deleted:
        try:
            await run_in_threadpool(cloudinary.uploader.destroy, picture_to_be_deleted)
        except Exception as e:
            # À la place, on log l'erreur pour que l'admin nettoie Cloudinary plus tard, 
            # sans bloquer l'expérience de l'utilisateur qui voit son événement bien supprimé.
            print(f"[WARNING] Impossible de supprimer l'image Cloudinary {picture_to_be_deleted}: {str(e)}")

    # 3. Notification et Redirection
    request.session["success"] = "🎉 Événement supprimé avec succès !"
    return RedirectResponse("/event_list", status_code=303)

@Root.get("/events/{event_id}/pictures")
async def render_event_pictures_page(
    request: Request,
    event_id: str,
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupérer l'événement
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalars().first()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Événement non trouvé"
        )

    # 2. Récupérer la liste des images déjà enregistrées pour cet événement
    pictures_result = await db.execute(
        select(EventPictures).where(EventPictures.event_id == event_id)
    )
    existing_pictures = pictures_result.scalars().all()

    # 3. Générer ou récupérer le token CSRF
    # Adapte selon la méthode de ton projet (ex: request.state.csrf_token)
    csrf_token = getattr(request.state, "csrf_token", "")

    # 4. Rendu du template Jinja2
    return templates.TemplateResponse(
        "Authentification/admin/event/Pictures/list/index.html",  # Remplace par le nom exact de ton fichier HTML
        {
            "request": request,
            "event": event,
            "existing_pictures": existing_pictures,
            "csrf_token": csrf_token
        }
    )

@Root.post("/register/picture", status_code=status.HTTP_201_CREATED)
async def create_event_picture(
        payload: schemas.EventPictureCreate,  # FastAPI lit directement le JSON envoyé par fetch
        request: Request,
        db: AsyncSession = Depends(connecting)
    ):
        # 1. Vérification de l'événement
        result = await db.execute(select(Event).where(Event.id == payload.event_id))
        event = result.scalars().first()
        
        if not event:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Événement non trouvé"
            )

        # 2. Création de l'image
        new_picture = EventPictures(
            id=str(uuid.uuid4()),
            event_id=payload.event_id,
            url=str(payload.url)
        )

        # 3. Enregistrement
        db.add(new_picture)
        await db.commit()
        await db.refresh(new_picture)

        return {
            "message": "Image enregistrée avec succès",
            "picture": {
                "id": new_picture.id,
                "event_id": new_picture.event_id,
                "url": new_picture.url
            }
        }

    # @Root.delete("/delete/pictures/{picture_id}", status_code=status.HTTP_200_OK)
    # async def delete_event_picture(
    #     picture_id: str,
    #     x_csrf_token: str = Header(None, alias="X-CSRF-Token"),
    #     db: AsyncSession = Depends(connecting)
    # ):
    #     # 1. Vérification CSRF
    #     if not x_csrf_token:
    #         raise HTTPException(
    #             status_code=status.HTTP_403_FORBIDDEN,
    #             detail="Token CSRF manquant"
    #         )

    #     # 2. Recherche en base de données
    #     result = await db.execute(
    #         select(EventPictures).where(EventPictures.id == picture_id)
    #     )
    #     picture = result.scalars().first()

    #     if not picture:
    #         raise HTTPException(
    #             status_code=status.HTTP_404_NOT_FOUND,
    #             detail="Image introuvable"
    #         )

    #     # 3. Extraction du Public ID et suppression sur Cloudinary
    #     public_id = extract_public_id_from_url(picture.url)
    #     cloudinary_deleted = False

    #     if public_id:
    #         try:
    #             # Appel à l'API Cloudinary pour détruire le fichier
    #             response = cloudinary.uploader.destroy(public_id)
    #             if response.get("result") == "ok":
    #                 cloudinary_deleted = True
    #         except Exception as e:
    #             # Tu peux logger l'erreur sans forcément bloquer la suppression BDD
    #             print(f"⚠️ Erreur lors de la suppression Cloudinary: {e}")

    #     # 4. Suppression en BDD
    #     await db.delete(picture)
    #     await db.commit()

    #     return {
    #         "message": "Image supprimée avec succès",
    #         "deleted_id": picture_id,
    #         "cloudinary_deleted": cloudinary_deleted
    #     }

# Fonction utilitaire pour extraire le public_id depuis une URL Cloudinary
def extract_public_id(url_or_id: str) -> str:
    """
    Transforme : https://res.cloudinary.com/cloud_name/image/upload/v123456/folder/sample.jpg
    En : folder/sample
    """
    if not url_or_id:
        return ""
    if not url_or_id.startswith("http"):
        return url_or_id # C'est déjà un public_id

    # Pattern regex pour isoler le public_id de l'URL
    match = re.search(r'/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$', url_or_id)
    if match:
        return match.group(1)
    return url_or_id

@Root.delete("/pictures/{picture_id}")
async def delete_picture(
    picture_id: str, 
    request: Request,
    db: AsyncSession = Depends(connecting)  # Remplacez par votre dépendance de session DB
):
    """Route pour supprimer une image hébergée sur Cloudinary."""
    stmt = (select(EventPictures).where(EventPictures.id == picture_id))
    result = await db.execute(stmt)
    picture = result.scalars().first()
    if not picture:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Image non trouvée"
        )
    public_id = extract_public_id(picture.url)
    if public_id:
        try:
            cloud_res = cloudinary.uploader.destroy(public_id)
            # On log la réponse Cloudinary
            print(f"Cloudinary response for {public_id}: {cloud_res}")
        except Exception as e:
            # On log l'erreur mais on ne bloque pas la suppression en BDD si l'image n'existe plus sur Cloudinary
            print(f"Avertissement Cloudinary : {str(e)}")
    #4. Suppression dans la base de données (SQLAlchemy Async)
    try:
        await db.delete(picture)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la suppression en BDD : {str(e)}"
        )

    return {
        "status": "success",
        "message": "Image supprimée avec succès",
        "id": picture_id
    }

@Root.get("/download/list_guest/{event_id}/export_excel") #endpoint pour le telechargement du fichier des invités
async def downloadGuestList(request:Request,event_id:str,db:AsyncSession = Depends(connecting),user=permission_required("view_guest")):
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    if not event:
        raise HTTPException(404,"event not found")
    list_guests =(select(Guest).where(Guest.event_id == event_id).options(selectinload(Guest.event)))
    res = await db.execute(list_guests)
    event_guests = res.scalars().all()
    if not event_guests :
        guestNotFound = True
        return templates.TemplateResponse("Event/Home/mainEventView.html",{'request':request,'guestNotFound':guestNotFound,"event":'',"guests":event_guests})
    wb = Workbook() #create a workbook
    ws = wb.active #active it
    ws.title = "liste_des_invites" #filename
        #head of tables
    ws.append([
        "Nom de l'invité",
        "Telephone",
        "Email",
        "Type",
        "Code d'acces",
        "Table",
        "Etat"
    ])
    for guest in event_guests:
        if(guest.is_present ):
            presence = "present"
        else:
            presence = "absent"
        ws.append([
            guest.name or "",
            guest.telephone or "",
            guest.email or "",
            guest.guest_type or "",
            guest.get_pass or "",
            guest.place or "",
            presence 
            ])
    file_stream = BytesIO() #create a stream in the memory (ram)
    await run_in_threadpool(wb.save,file_stream) #save the workbook in the memory (ram)
    file_stream.seek(0) #move the cursor to the beginning of the stream
    safe_filename = quote(f"liste_des_invites_{event.name}.xlsx") #encode the filename to be safe for the header
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
         "Content-Disposition": f"attachment; filename*='UTF-8''{safe_filename}"
        }
    )

@Root.get("/download/presence/{event_id}/export_excel")#endpoint pour le telechargement du fichier de confirmation des invités
async def getPresenceList(request:Request,event_id:str,db:AsyncSession = Depends(connecting),user=Depends(permission_required("view_guest"))):
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    if not event:
        raise HTTPException(404,"event not found")
    curent_event_guests =(select(Guest).where(Guest.event_id == event_id).options(selectinload(Guest.event),selectinload(Guest.invite).selectinload(Invite.guestResponse)))
    res = await db.execute(curent_event_guests)
    event_guests = res.scalars().all()
    if not event_guests :
        raise HTTPException(404,"event not found")
    event= event_guests[0].event if event_guests else None
    wb = Workbook()
    ws = wb.active
    ws.title = "La liste de presence d'invité"
    ws.append([
        "Nom de l'invité",
        "Numero",
        "Present"
    ])
    for gst in event_guests:
        response = None
        if gst.invite and gst.invite.guestResponse:
            response = gst.invite.guestResponse.response
        ws.append([
            gst.name or "inconnu",
            gst.telephone or "N/A",
             response
         ])
    memory = BytesIO()
    await run_in_threadpool(wb.save,memory) #save the workbook in the memory (ram)
    memory.seek(0)
    safe_filename = quote(f"liste_des_presence_pour_event_{event.name}.xlsx") #encode the filename to be safe for the header
    return StreamingResponse(
         memory,
         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         headers={
            "Content-Disposition": f"attachment; filename*='UTF-8''{safe_filename}"
         }
     )

#==========================================================routes de programme

@Root.get("/event/{event_id}/program")
async def get_program_view(
    request: Request,
    event_id: str,
    db: AsyncSession = Depends(connecting),
):
    # 2. Récupération de tous les événements si nécessaire pour une liste déroulante
    result = await db.execute(select(Event).order_by(Event.id.desc()))
    events = result.scalars().all()

    # 3. Récupération des données en session
    success_message = request.session.pop("success_message", None)
    event_error = request.session.pop("event_error", None)
    form_data_session = request.session.pop("form_data", None)

    # 4. Structure par défaut des données de formulaire
    if form_data_session is None:
        form_data = {
            "errors": {
                "title": "",
                "time": "",
                "description": "",
                "start_date": "",
                "end_date": "",
            },
            "fields": {
                "title": "",
                "time": "",
                "event_id": event_id,  # On peut pré-remplir l'event_id
                "description": "",
                "start_date": "",
                "end_date": "",
            },
        }
    else:
        form_data = form_data_session

    # 5. Gestion CSRF
    csrf_token = secrets.token_urlsafe(32)

    # 6. Rendu Jinja2 avec 'event' inclus dans le contexte
    response = templates.TemplateResponse(
        "Authentification/admin/event/forms/program_form/program_form.html",
        {
            "request": request,
            "event_id": event_id,  # <-- Ajouté pour exploiter l'événement dans le template
            "events": events,
            "success": success_message,
            "event_error": event_error,
            "csrf_token": csrf_token,
            "data": form_data,
        },
    )

    # 7. Définition du cookie CSRF (httponly doit être True pour la sécurité)
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,
        samesite="lax",
        secure=False,  # Passez à True en production (HTTPS)
        path="/",
    )

    return response

@Root.post("/programs/create")
@limiter.limit("20/minute")
async def create_program(
    request: Request,
    event_id: str = Form(...),              
    title: str = Form(...),
    time: str = Form(...),
    start_date: str = Form(...),  # Récupéré au format ISO (ex: "2026-08-15T10:00")
    end_date: str = Form(...),
    description: str = Form(None),
    csrf_token: str = Form(...),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    # 1. Nettoyage & Normalisation des données
    clean_title = title.strip()             # 👈 Conservation de la casse d'origine
    clean_time = time.strip()
    clean_description = description.strip() if description and description.strip() else None
    form_data={
        "errors": {
            "title": " le titre est obligatoire et doit contenir entre 2 et 250 caractères." if len(clean_title) < 2 or len(clean_title) > 250 else "",
            "time": " l'heure est obligatoire et contenir entre 50 caractères.." if len(clean_time) < 1 or len(clean_time) > 50 else "",
            "start_date": "La date de début doit etre antérieure à la date de fin." if start_date and end_date and start_date > end_date else "",
            "end_date": "La date de fin est obligatoire." if not end_date else "",
            "description": ""
        },
        "fields": {
            "title": title,
            "time": time,
            "event_id": event_id,
            "start_date": start_date,
            "end_date": end_date,
            "description": description
        },
    }

    if any(form_data["errors"].values()):
        request.session['form_data'] = form_data
        return RedirectResponse(f"/event/{event_id}/program", status_code=303)
    if (start_date and datetime.fromisoformat(start_date) < datetime.now()) or (end_date and datetime.fromisoformat(end_date) < datetime.now()) :
        request.session['form_data'] = form_data
        request.session['event_error'] = "Les dates doivent être supérieures à la date actuelle."
        return RedirectResponse(f"/event/{event_id}/program", status_code=303)
    try:
        dt_start = datetime.fromisoformat(start_date)
        dt_end = datetime.fromisoformat(end_date)
    except ValueError:
        # Gérer le cas où la date transmise est invalide
        return templates.TemplateResponse(
            "Authentification/admin/event/forms/event_form.html",
            {
                "request": request,
                "message": "Le format des dates est invalide.",
                "csrf_token": csrf_token
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )
    # 3. Vérification de l'existence de l'événement en BDD
    event_check = await db.execute(select(Event).where(Event.id == event_id))
    event = event_check.scalars().first()

    if not event:
        events_res = await db.execute(select(Event).order_by(Event.id.desc()))
        return templates.TemplateResponse(
            "Authentification/admin/event/forms/program_form.html",
            {
                "request": request,
                "events": events_res.scalars().all(),
                "message": "L'événement sélectionné n'existe pas.",
                "csrf_token": csrf_token
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # 4. Création et enregistrement du Program
    new_program = Program(
        event_id=event_id,
        title=clean_title,
        time=clean_time,
        start_date=dt_start,
        end_date=dt_end,
        description=clean_description
    )

    try:
        db.add(new_program)
        await db.commit()
    except Exception as e:
            await db.rollback()
            print(f"🚨 [PROD DB ERROR] : {str(e)}")
            raise HTTPException(status_code=500, detail="Erreur lors de la modification de l'événement")

    # 5. Redirection avec message Flash dans la session
    request.session["success_message"] = "Programme créé avec succès !"
    
    return RedirectResponse(
        url=f"/event/{event_id}/program", 
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.get("/programs/list/{event_id}")
async def list_programs(
    request: Request,
    event_id: str,
    success: Optional[str] = None,
    db: AsyncSession = Depends(connecting)
):
    
    # 1. Récupération de l'événement
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()

    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    # 2. Récupération des programmes associés à l'événement
    programs_res = await db.execute(select(Program).where(Program.event_id == event_id).options(selectinload(Program.event)))
    programs = programs_res.scalars().all()
    # 3. Rendu du template avec les programmes et l'événement
    return templates.TemplateResponse(
        "Authentification/admin/event/program/list_programs.html",
        {
            "request": request,
            "event": event,
            "programs": programs,
            "success": success,
        }
    )


    # Affichage du formulaire de modification
@Root.get("/program/{program_id}/edit")
async def edit_program_form(
    request: Request,
    program_id: str,
    db: AsyncSession = Depends(connecting)
):
    # Récupérer le programme avec ses informations
    prog_query = await db.execute(select(Program).where(Program.id == program_id))
    program = prog_query.scalar_one_or_none()

    if not program:
        raise HTTPException(status_code=404, detail="Programme non trouvé")

    # Récupérer la liste des événements pour le sélecteur
    events_query = await db.execute(select(Event))
    events = events_query.scalars().all()
    return templates.TemplateResponse(
        "Authentification/admin/event/forms/program_form/edit_program.html",
        {
            "request": request,
            "program": program,
            "events": events,
    
            "data": {"fields": {}, "errors": {}}
        }
    )


# Traitement de la soumission du formulaire HTML
@Root.post("/program/{program_id}/update")
async def update_program_form(
    request: Request,
    program_id: str,
    event_id: str = Form(...),
    title: str = Form(...),
    time: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(connecting)
):
    prog_query = await db.execute(select(Program).where(Program.id == program_id))
    program = prog_query.scalar_one_or_none()

    events_query = await db.execute(select(Event))
    events = events_query.scalars().all()

    # Conversion et validation des dates
    try:
        parsed_start = datetime.fromisoformat(start_date)
        parsed_end = datetime.fromisoformat(end_date)
    except ValueError:
        return templates.TemplateResponse(
            "Authentification/admin/event/forms/program_form/edit_program.html",
            {
                "request": request,
                "program": program,
                "events": events,
                "message": "Format de date invalide.",
                "data": {"fields": request._form, "errors": {}}
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    if parsed_end < parsed_start:
        return templates.TemplateResponse(
            "edit_program.html",
            {
                "request": request,
                "program": program,
                "events": events,
                "data": {
                    "fields": request._form,
                    "errors": {"end_date": "La date de fin doit être postérieure au début."}
                }
            },
            status_code=status.HTTP_400_BAD_REQUEST
        )

    # Application des modifications
    program.event_id = event_id
    program.title = title
    program.time = time
    program.start_date = parsed_start
    program.end_date = parsed_end
    program.description = description

    try:
        await db.commit()
        await db.refresh(program)
    except Exception:
        await db.rollback()
        return templates.TemplateResponse(
            "edit_program.html",
            {
                "request": request,
                "program": program,
                "events": events,
                "message": "Une erreur serveur est survenue lors de la mise à jour."
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Redirection Post-Redirect-Get vers la liste des programmes
    return RedirectResponse(
        url=f"/programs/list/{program.event_id}?success=Programme+mis+%C3%A0+jour+avec+succ%C3%A8s",
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.post("/program/{program_id}/delete", response_class=RedirectResponse)
async def delete_program(
    program_id: str,
    db: AsyncSession = Depends(connecting)
):
    try:
        # 1. Recherche du programme en base de données
        query = await db.execute(select(Program).where(Program.id == program_id))
        program = query.scalar_one_or_none()

        # 2. Gestion si le programme n'existe pas
        if not program:
            logger.warning(f"Tentative de suppression d'un programme inexistant ID: {program_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Programme non trouvé"
            )

        event_id = program.event_id  # Conserve l'ID de l'événement pour la redirection

        # 3. Suppression
        await db.delete(program)
        await db.commit()

        logger.info(f"Programme ID {program_id} supprimé avec succès.")

        # 4. Redirection vers la liste des programmes avec message de succès
        redirect_url = f"/programs/list/{event_id}?success=Programme+supprimé+avec+succès"
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Erreur lors de la suppression du programme {program_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur interne est survenue lors de la suppression."
        )

