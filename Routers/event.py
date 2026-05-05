#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,UploadFile,File,Cookie
from fastapi.responses import RedirectResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from uuid import uuid4
import os,cloudinary,cloudinary.uploader
from db_setting import engine,connecting
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
from config import secret,algo
from urllib.parse import quote

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static
Pictures = "static/Pictures/{None}"
os.makedirs("Pictures",exist_ok=True)

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
async def searchEvent(request:Request,researched_event:str,db:AsyncSession = Depends(connecting)):
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
    get_event =await db.execute(select(Event).where(Event.group_id == group_id).options(selectinload(Event.guests)).order_by(desc(Event.created_date)))
    events = get_event.scalars().all()
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":events,'curent_user_role':user_role})

@Root.get("/event_description/{event_id}",name="main_event")#get the mainEventView
async def getEventForm(request:Request,event_id :str,
                       access_token=Cookie(None),
                       db:AsyncSession = Depends(connecting)):
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
    return templates.TemplateResponse("Event/Home/mainEventView.html",{'request':request,"event":event,"total":total,'current_user_role':user_role})

@Root.get("/detail/event/{event_id}")#la root pour voir les detail d'un event
async def eventDetail(request:Request,event_id : str,access_token = Cookie(None),db:AsyncSession = Depends(connecting)):
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles),selectinload(User.groups)))
    user = user_res.scalars().first()
    for role in user.roles:
        user_role = role.name
    get_Event = await db.execute(select(Event).where(Event.id == event_id))
    event = get_Event.scalars().first()
    return templates.TemplateResponse("Event/List/detail.html",{'request':request,"event":event,'curent_user_role':user_role})

@Root.get("/event_form",name="event_form")#event form request
def getEventForm(request:Request,user=Depends(permission_required("create_event"))):
    return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request})

@Root.post("/create_event") #create an event
async def creatEvent(request:Request,eventName:str = Form(...),
eventType:str =Form(...), eventDate: datetime = Form(...),
eventAddress:str = Form(),eventDescription: Optional[str] = Form(None),
location:str = Form(...),
photo:UploadFile = File(None),
user=Depends(permission_required("create_event")),
couple_name :str = Form(None),
couple_phone_number :str = Form(...),
access_token =Cookie(None),
is_active : bool = Form(None),#le cadeau
language :str = Form(...),#la langue
organizer :str = Form(None),#organisateeur
greetings:str = Form(None),#message de bienvenu
Db:AsyncSession = Depends(connecting)):
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await Db.execute(select(User).where(User.id == user_id).options(selectinload(User.groups),selectinload(User.roles)))
    user = user_res.scalars().first()
    group_id = None
    user_role = None #le role de l'utilisateur sera none par defaut pour eviter les erreurs
    is_event_photo =  False
    photo_url,photo_public_id = None,None
    if user.groups:
        group_id = user.groups[0].id if user.groups else None
        user_role = user.roles[0].name if user.roles else None
    if eventDate < datetime.now():
        return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"dateError":' Entrez une date superieur a la date actuelle ou entrer une date correcte  !!!',
            'eventName':eventName, 'eventType':eventType,'couple_name':couple_name,'location':location,'is_active':is_active,'couple_phone_number':couple_phone_number, 'eventDate':eventDate, 'eventAddress':eventAddress,'organizer':organizer,'greetings':greetings, 'eventDescription':eventDescription}, status_code=400)
    if photo and photo.filename:
        if not photo.content_type or not photo.content_type.startswith("image/"):
            return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"img_error":' le fichier doit etre une image !!!',
            'eventName':eventName, 'eventType':eventType, 'eventDate':eventDate, 'eventAddress':eventAddress, 'eventDescription':eventDescription
            },status_code=400)
    try:
        if photo and photo.filename:
            if eventType =="Mariage":
                upload_result = await run_in_threadpool(cloudinary.uploader.upload,photo.file,folder = "EasyInvite/wedding_events",transformation = [{'width':1000,'height':1000,'crop':'limit'},{'quality':"auto"}])
                photo_url = upload_result['secure_url']
                photo_public_id = upload_result['public_id']
            elif eventType =="birth_day":
                upload_result = await run_in_threadpool(cloudinary.uploader.upload,photo.file,folder = "EasyInvite/birth_day_events",transformation = [{'width':1000,'height':1000,'crop':'limit'},{'quality':"auto"}])
                photo_url = upload_result['secure_url']
                photo_public_id = upload_result['public_id']
            elif eventType =="conference":
                upload_result = await run_in_threadpool(cloudinary.uploader.upload,photo.file,folder = "EasyInvite/conference_events",transformation = [{'width':1000,'height':1000,'crop':'limit'},{'quality':"auto"}])
                photo_url = upload_result['secure_url']
                photo_public_id = upload_result['public_id']
            elif eventType =="concours":
                upload_result = await run_in_threadpool(cloudinary.uploader.upload,photo.file,folder = "EasyInvite/concours_events",transformation = [{'width':1000,'height':1000,'crop':'limit'},{'quality':"auto"}])
                photo_url = upload_result['secure_url']
                photo_public_id = upload_result['public_id']
    except Exception as e:
        raise HTTPException(status_code=500,detail=f"Erreur lors du téléchargement de l'image: {str(e)}")
    try:
        newEvent = Event(
        name = eventName,
        type = eventType,
        date = eventDate,
        address = eventAddress,
        description = eventDescription,
        location = location,
        couple_name = couple_name,
        couple_phone_number = couple_phone_number,
        created_by = user_id,
        guest_present = is_active if is_active else None,
        group_id = group_id,
        photo_url = photo_url if photo_url else None,
        photo_public_id=photo_public_id if photo_public_id else None,
        language=language,
        organizer=organizer,
        greeting_message = greetings,
            )
        Db.add(newEvent)
        await Db.commit()
        await Db.refresh(newEvent)
    except Exception :
        await Db.rollback()
        raise HTTPException(status_code=500,detail="Erreur lors de la création de l'événement")
    request.session["success"] = "🎉 Événement créé avec succès !"
    return RedirectResponse("/event_list",status_code=303)

@Root.get("/edit_event/{event_id}")#la root pour la modification d'un evenement
async def editEvent(request:Request,event_id : str,user=Depends(permission_required("edit_event")),db:AsyncSession = Depends(connecting)):
    edit_Event = select(Event).where(Event.id == event_id)
    res = await db.execute(edit_Event)
    editEvent = res.scalars().first()
    success = request.session.pop("success",None)
    return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"event":editEvent,"success":success})

@Root.post("/edit_event/{event_id}")#la root pour modifier un evenement
async def editEvent(request:Request,event_id : str,access_token = Cookie(None),eventName:str = Form(...),coupleName:str = Form(...),couple_phone_number:str = Form(...),eventType:str = Form(...),eventDate: str = Form(...),
                    eventAddress:str = Form(...),location:str = Form(...),eventDescription: Optional[str] = Form(None),
                    eventState: str = Form(...),photo:UploadFile = File(None),is_active:bool = Form(None),language:str = Form(...),organizer:str = Form(None),greetings:str = Form(None),db:AsyncSession = Depends(connecting)
                    ,user=Depends(permission_required("edit_event"))):
    edited_Event_Data = select(Event).where(Event.id == event_id)
    res = await db.execute(edited_Event_Data)
    editedEventData = res.scalars().first() 
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.groups)))
    user = user_res.scalars().first()
    if user.groups:
        group_id = editedEventData.group_id
    for role in user.roles:
            user_role = role.name
    if user_role != "admin":
        groups_res = await db.execute(select(Group).where(Group.id == group_id))
        groups = groups_res.scalars().first()
    try:
        parsed_modified_date = datetime.fromisoformat(eventDate)
        if(parsed_modified_date < datetime.now()):
            return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"dateError":'La date doit etre superieur a l\'actuelle !!!','event':editedEventData}, status_code=400)
    except (ValueError,TypeError):
        return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,'error':'veillez entrer une date correcte','event':editedEventData},status_code=400)
    if not editedEventData:
        raise HTTPException(status_code=400,detail="Evenement intouvable")
    event_photo_public_id = editedEventData.photo_public_id
    photo_url = editedEventData.photo_url
    photo_public_id = editedEventData.photo_public_id
    if photo and photo.filename:#si la photo a ete envoye
        if not photo.content_type or not photo.content_type.startswith("image/"):#si ce n'est pas une image
            return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"img_error":' le fichier doit etre une image !!!','event':editedEventData},status_code=400)
        try:
            if event_photo_public_id:
                if eventType =="Mariage":
                    await run_in_threadpool(cloudinary.uploader.destroy,event_photo_public_id)
                elif eventType =="birth_day":
                    await run_in_threadpool(cloudinary.uploader.destroy,event_photo_public_id)
            if eventType == "Mariage" and not event_photo_public_id:
                upload_result =await run_in_threadpool(cloudinary.uploader.upload,photo.file,folder = "EasyInvite/wedding_events",transformation = [{'width':1000,'height':1000,'crop':'limit'},{'quality':"auto"}])
                photo_url= upload_result['secure_url']
                photo_public_id = upload_result['public_id']
            elif eventType == "birth_day" and not event_photo_public_id:
                upload_result =await run_in_threadpool(cloudinary.uploader.upload,photo.file,folder = "EasyInvite/birth_day_events",transformation = [{'width':1000,'height':1000,'crop':'limit'},{'quality':"auto"}])
                photo_url= upload_result['secure_url']
                photo_public_id = upload_result['public_id']
        except Exception as e:
            raise HTTPException(status_code=500,detail=f"Erreur lors du téléchargement de l'image: {str(e)}") 
    editedEventData.name = eventName
    editedEventData.couple_name = coupleName
    editedEventData.couple_phone_number = couple_phone_number
    editedEventData.type = eventType
    editedEventData.date = parsed_modified_date
    editedEventData.address = eventAddress
    editedEventData.location = location
    editedEventData.description = eventDescription
    editedEventData.state = eventState
    editedEventData.guest_present = is_active if is_active else None
    editedEventData.created_by = user_id
    editedEventData.photo_public_id = photo_public_id 
    editedEventData.photo_url = photo_url  
    editedEventData.organizer = organizer
    editedEventData.language = language
    editedEventData.greeting_message = greetings
    if user_role != "admin":
        edited_Event_Data.groups = [groups]
    edited_Event_Data.groups = []
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500,detail="Erreur lors de la modification de l'événement")
    request.session["success"] = "🎉 Événement modifié avec succès !"
    return RedirectResponse("/event_list",status_code=303)

@Root.post("/delete_event/{event_id}")
async def deleteEvent(request:Request,event_id:str,user=Depends(permission_required("delete_event")),db:AsyncSession = Depends(connecting)):
    event_to_delete =select(Event).where(Event.id==event_id)
    res = await db.execute(event_to_delete)
    eventToDelete = res.scalars().first()
    if not eventToDelete:
        raise HTTPException(status_code=404,detail="cette evenement n'existe pas")
    Picture_to_be_deleted= eventToDelete.photo_public_id #recuprer l'addresse de l'image a supprimer
    try:
        await db.delete(eventToDelete)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500,detail="Erreur lors de la suppression de l'événement")
    if Picture_to_be_deleted:
        try:
            await run_in_threadpool(cloudinary.uploader.destroy,Picture_to_be_deleted)
        except Exception as e:
            raise HTTPException(status_code=500,detail=f"Erreur lors de la suppression de l'image: {str(e)}")
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500,detail="Erreur lors de la suppression de l'événement")
    request.session["success"] = "🎉 Événement supprimé avec succès !"
    return RedirectResponse("/event_list",status_code=303)

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

