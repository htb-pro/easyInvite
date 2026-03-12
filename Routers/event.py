#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,UploadFile,File,Cookie
from fastapi.responses import HTMLResponse,RedirectResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import os,shutil
from db_setting import engine,connecting
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from models import *
from datetime import date
from jose import jwt
from typing import Optional
from datetime import datetime,date
from openpyxl import Workbook
from io import BytesIO
from Routers.loging import get_current_user_from_cookie
from app.security.permissions import permission_required,has_permission
from config import secret,algo

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static
Pictures = "static/Pictures/{None}"
os.makedirs("Pictures",exist_ok=True)

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
            get_event =await db.execute(select(Event).options(selectinload(Event.guests)))
            events = get_event.scalars().all()
            return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":events,'curent_user_role':user_role})
    get_event =await db.execute(select(Event).where(Event.group_id == group_id).options(selectinload(Event.guests)))
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
async def creatEvent(request:Request,eventName:str = Form(),
eventType:str =Form(...), eventDate: datetime = Form(),
eventAddress:str = Form(),eventDescription: Optional[str] = Form(None),
location:str = Form(...),
photo:UploadFile = File(),
user=Depends(permission_required("create_event")),
couple_name :str = Form(None),
access_token =Cookie(None),
is_active : bool = Form(None),#le cadeau
Db:AsyncSession = Depends(connecting)):
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await Db.execute(select(User).where(User.id == user_id).options(selectinload(User.groups),selectinload(User.roles)))
    user = user_res.scalars().first()
    group_id = None
    user_role = None #le role de l'utilisateur sera none par defaut pour eviter les erreurs
    serie = generate_serie(eventName)
    if user.groups:
        for group in user.groups:
            group_id = group.id
        for role in user.roles:
            user_role = role.name
    try:
        if eventDate < datetime.now():
             return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"dateError":' Entrez une date superieur a la date actuelle !!!',
            'eventName':eventName, 'eventType':eventType, 'eventDate':eventDate, 'eventAddress':eventAddress, 'eventDescription':eventDescription}, status_code=400)
    except (TypeError,ValueError):
        return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"error":' Entrer une date correcte !!!',
        'eventName':eventName, 'eventType':eventType, 'eventDate':eventDate, 'eventAddress':eventAddress, 'eventDescription':eventDescription
        },status_code=400)
    newEvent = Event(
        name = eventName,
        type = eventType,
        date = eventDate,
        address = eventAddress,
        description = eventDescription,
        location = location,
        couple_name = couple_name,
        created_by = user_id,
        guest_present = is_active if is_active else None,
        group_id = group_id,
        serie = serie
    )
    Db.add(newEvent)
    await Db.commit()
    await Db.refresh(newEvent)
    event_img_doc = newEvent.id
    event_picture = os.path.basename(photo.filename) #la phone
    if event_picture:
        Pictures = f"static/Pictures/{event_img_doc}"#l'adresse du stockage de l'image
        os.makedirs(Pictures,exist_ok=True)#creer un dosier s'il n'existe pas 
        filepath = os.path.join(Pictures,event_picture)#precision de l'adresse relative de l'image
        with open(filepath,"wb") as buffer :
            shutil.copyfileobj(photo.file,buffer)
    request.session["success"] = "🎉 Événement créé avec succès !"
    return RedirectResponse("/event_list",status_code=303)

@Root.get("/edit_event/{event_id}")#la root pour la modification d'un evenement
async def editEvent(request:Request,event_id : str,user=Depends(permission_required("edit_event")),db:AsyncSession = Depends(connecting)):
    edit_Event = select(Event).where(Event.id == event_id)
    res = await db.execute(edit_Event)
    editEvent = res.scalars().first()
    return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"event":editEvent})

@Root.post("/edit_event/{event_id}")#la root pour modifier un evenement
async def editEvent(request:Request,event_id : str,access_token = Cookie(None),eventName:str = Form(...),coupleName:str = Form(...),eventType:str = Form(...),eventDate: str = Form(...),
                    eventAddress:str = Form(...),location:str = Form(...),eventDescription: Optional[str] = Form(None),
                    eventState: str = Form(...),photo:UploadFile = File(),is_active:bool = Form(None),db:AsyncSession = Depends(connecting)
                    ,user=Depends(permission_required("edit_event"))):
    edited_Event_Data = select(Event).where(Event.id == event_id)
    res = await db.execute(edited_Event_Data)
    editedEventData = res.scalars().first() 
    res = jwt.decode(access_token,secret,algorithms=[algo])
    user_id = res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.groups)))
    user = user_res.scalars().first()
    serie = generate_serie(eventName)
    if user.groups:
        group_id = editedEventData.group_id
    for role in user.roles:
            user_role = role.name
    if user_role != "admin":
        groups_res = await db.execute(select(Group).where(Group.id == group_id))
        groups = groups_res.scalars().first()
    loaded_image = photo.filename
    if loaded_image :#si une photo a ete chargee
        edited_event_img_doc = event_id
        Pictures = f"static/Pictures/{edited_event_img_doc}"#l'adresse de l'emplacement ou il y aura l'image
        os.makedirs(Pictures,exist_ok=True) #creer le dossier d'emplacement s'il n'existe pas
        images = os.listdir(Pictures)# prends toutes les images se trouves dans static/pictures
        for img in images: #pour une image existante dans le dossier 
            os.remove(os.path.join(Pictures,img))#tu le supprime
        file_path = os.path.join(Pictures,loaded_image)
        with open(file_path,"wb") as buffer:
                        shutil.copyfileobj(photo.file,buffer)
    try:
        parsed_modified_date = datetime.fromisoformat(eventDate)
        if(parsed_modified_date < datetime.now()):
            return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"dateError":'La date doit etre superieur a l\'actuelle !!!','event':editedEventData}, status_code=400)
    except (ValueError,TypeError):
        return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,'error':'veillez entrer une date correcte','event':editedEventData},status_code=400)

    if not editedEventData:
        raise HTTPException(status_code=400,detail="Evenement intouvable")
    editedEventData.name = eventName
    editedEventData.couple_name = coupleName
    editedEventData.type = eventType
    editedEventData.date = parsed_modified_date
    editedEventData.address = eventAddress
    editedEventData.location = location
    editedEventData.description = eventDescription
    editedEventData.state = eventState
    editedEventData.guest_present = is_active if is_active else None
    editedEventData.created_by = user_id
    editedEventData.serie = serie
    if user_role != "admin":
        edited_Event_Data.groups = [groups]
    edited_Event_Data.groups = []
    await db.commit()
    return RedirectResponse("/event_list",status_code=303)

@Root.post("/delete_event/{event_id}")
async def deleteEvent(request:Request,event_id:str,user=Depends(permission_required("delete_event")),db:AsyncSession = Depends(connecting)):
    event_to_delete =select(Event).where(Event.id==event_id)
    res = await db.execute(event_to_delete)
    eventToDelete = res.scalars().first()
    if not eventToDelete:
        raise HTTPException(status_code=404,detail="cette evenement n'existe pas")
    Pictures= f"static/Pictures/{event_id}"#dossier de l'image de l'evenement
    is_dir_exist = os.path.exists(Pictures)#exist il ?
    if is_dir_exist: #si oui 
        shutil.rmtree(Pictures)#qu'il soit supprimer
    await db.delete(eventToDelete)
    await db.commit()
    return RedirectResponse("/event_list",status_code=303)

@Root.get("/download/list_guest/{event_id}/export_excel") #endpoint pour le telechargement du fichier des invités
async def downloadGuestList(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    event_list_guests =(select(Guest).where(Guest.event_id == event_id).options(selectinload(Guest.event)))
    res = await db.execute(event_list_guests)
    event_guests = res.scalars().all()
    event = event_guests[0].event if event_guests else None
    wb = Workbook() #create a workbook
    ws = wb.active #active it
    ws.title = "liste_des_invites" #filename
    if not event_guests :
        guestNotFound = True
        return templates.TemplateResponse("Event/Home/mainEventView.html",{'request':request,'guestNotFound':guestNotFound,"event":'',"guests":event_guests})
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
            guest.name,
            guest.telephone,
            guest.email,
            guest.guest_type,
            guest.get_pass,
            guest.place,
            presence 
            ])
    file_stream = BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
         "Content-Disposition": f"attachment; filename=liste_des_invites_{event.name}.xlsx"
        }
    )

@Root.get("/download/presence/{event_id}/export_excel")#endpoint pour le telechargement du fichier de confirmation des invités
async def getPresenceList(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
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
            gst.name,
            gst.telephone,
             response
         ])
    memory = BytesIO()
    wb.save(memory) #save the sheet in memory (ram)
    memory.seek(0)
    return StreamingResponse(
         memory,
         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         headers={
            "Content-Disposition": f"attachment; filename=liste_des_presence_pour_event_{event.name}.xlsx"
         }
     )