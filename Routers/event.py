#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter
from fastapi.responses import HTMLResponse,RedirectResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import models
from db_setting import engine,connecting
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from models import *
from datetime import date
from typing import Optional
from datetime import datetime,date
from openpyxl import Workbook
from io import BytesIO
from Routers.loging import get_current_user_from_cookie

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static


@Root.get("/event_form",name="event_form")#event form request
def getEventForm(request:Request):
    return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request})

@Root.get("/event_description/{event_id}",name="main_event")#get the mainEventView
async def getEventForm(request:Request,event_id :str,
                       db:AsyncSession = Depends(connecting)):
    select_event =(select(Event).where(Event.id==event_id).options(selectinload(Event.guests)))
    get_guests = await db.execute(select_event)
    event = get_guests.scalars().first()
    total =len(event.guests)
    return templates.TemplateResponse("Event/Home/mainEventView.html",{'request':request,"event":event,"total":total})

@Root.get("/event_list/",name="event_list")#get the event list 
async def getEventList(request:Request,  db:AsyncSession = Depends(connecting)):
    selectEvent =(select(Event).options(selectinload(Event.guests)))
    get_list_events = await db.execute(selectEvent)
    events =get_list_events.scalars().all()
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":events})

@Root.get("/research_event")
async def searchEvent(request:Request,researched_event:str,db:AsyncSession = Depends(connecting)):
    get_event =(select(Event).where(Event.name.like(f"%{researched_event}%")).options(selectinload(Event.guests)))
    result = await db.execute(get_event)
    event = result.scalars().all()
    if not event :
        eventNotFound = "aucun evenement trouvé a ce nom" #message a afficher si l'evenement n'est pas trouve
        return templates.TemplateResponse("Event/List/list_event.html",{'request':request,'eventNotFound':eventNotFound,'event':event})
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":event})

@Root.post("/create_event") #create an event
async def creatEvent(request:Request,eventName:str = Form(),
eventType:str =Form(...), eventDate: str = Form(),
eventAddress:str = Form(),eventDescription: Optional[str] = Form(None),
Db:AsyncSession = Depends(connecting)):
    try:
        parsed_date = datetime.fromisoformat(eventDate)#la conversion d'une date chaine de caractere('2026-2-1') en format date(2026,2,1)
        if parsed_date < datetime.now():
             return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"dateError":' Entrez une date superieur a la date actuelle !!!',
            'eventName':eventName, 'eventType':eventType, 'eventDate':eventDate, 'eventAddress':eventAddress, 'eventDescription':eventDescription}, status_code=400)
    except (TypeError,ValueError):
        return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request,"error":' Entrer une date correcte !!!',
        'eventName':eventName, 'eventType':eventType, 'eventDate':eventDate, 'eventAddress':eventAddress, 'eventDescription':eventDescription
        },status_code=400)
    newEvent = Event(
        name = eventName,
        type = eventType,
        date = parsed_date,
        address = eventAddress,
        description = eventDescription
    )
    Db.add(newEvent)
    await Db.commit()
    await Db.refresh(newEvent)
    request.session["success"] = "🎉 Événement créé avec succès !"
    return RedirectResponse("/event_list",status_code=303)


@Root.get("/detail/{event_id}/")#la root pour voir les detail d'un event
async def eventDetail(request:Request,event_id : str,db:AsyncSession = Depends(connecting)):
    get_Event = (select(Event)).where(Event.id == event_id)
    result = await db.execute(get_Event)
    getEvent = result.scalars().first()
    return templates.TemplateResponse("Event/List/detail.html",{'request':request,"event":getEvent})

@Root.get("/edit_event/{event_id}")#la root pour la modification d'un evenement
async def editEvent(request:Request,event_id : str,db:AsyncSession = Depends(connecting)):
    edit_Event = select(Event).where(Event.id == event_id)
    res = await db.execute(edit_Event)
    editEvent = res.scalars().first()
    return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"event":editEvent})

@Root.post("/edit_event/{event_id}")#la root pour modifier un evenement
async def editEvent(request:Request,event_id : str,eventName:str = Form(...),eventType:str = Form(...),eventDate: str = Form(...),
                    eventAddress:str = Form(...),eventDescription: Optional[str] = Form(None),eventState: str = Form(...),db:AsyncSession = Depends(connecting)):
    edited_Event_Data = select(Event).where(Event.id == event_id)
    res = await db.execute(edited_Event_Data)
    editedEventData = res.scalars().first()
    try:
        parsed_modified_date = datetime.fromisoformat(eventDate)
        if(parsed_modified_date < datetime.now()):
            return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"dateError":'La date doit etre superieur a l\'actuelle !!!','event':editedEventData}, status_code=400)
    except (ValueError,TypeError):
        return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,'error':'veillez entrer une date correcte','event':editedEventData},status_code=400)

    if not editedEventData:
        raise HTTPException(status_code=400,detail="Evenement intouvable")
    editedEventData.name = eventName
    editedEventData.type = eventType
    editedEventData.date = parsed_modified_date
    editedEventData.address = eventAddress
    editedEventData.description = eventDescription
    editedEventData.state = eventState
    await db.commit()
    return RedirectResponse("/event_list",status_code=303)

@Root.post("/delete_event/{event_id}")
async def deleteEvent(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    event_to_delete =select(Event).where(Event.id==event_id)
    res = await db.execute(event_to_delete)
    eventToDelete = res.scalars().first()
    if not eventToDelete:
        raise HTTPException(status_code=404,detail="cette evenement n'existe pas")
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

@Root.get("/download/presence/{event_id}/export_excel")
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