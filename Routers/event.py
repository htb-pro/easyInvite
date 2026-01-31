#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import models
from db_setting import engine,connecting
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models import *
from datetime import date
from typing import Optional
from datetime import datetime,date

models.Base.metadata.create_all(bind=engine)


Root = APIRouter()


templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static

@Root.get("/event_form",name="event_form",response_class = HTMLResponse)#event form request
def getEventForm(request:Request):
    return templates.TemplateResponse("Event/Forms/event_form.html",{'request':request})

@Root.get("/event_description/{event_id}",name="main_event")#get the mainEventView
def getEventForm(request:Request,event_id :str,
                       event:Session = Depends(connecting),
                       db:Session = Depends(connecting)):
    eventDescription = event.query(Event).filter(Event.id == event_id).first()
    guests = db.query(Event).filter(Event.id == event_id).first()
    total = len(guests.guests)
    return templates.TemplateResponse("Event/Home/mainEventView.html",{'request':request,"event":eventDescription,"guests":guests,"total":total})

@Root.get("/event_list/",name="event_list")#get the mainEventView
def getEventList(request:Request,  db: Session = Depends(connecting)):
    events = db.query(Event).all()
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":events})

@Root.get("/research_event")
def searchEvent(request:Request,researched_event:str,db:Session = Depends(connecting)):
    event = db.query(Event).filter(Event.name.like(f"%{researched_event}%")).all()
    if not event :
        raise HTTPException(404,"evenement introuvable")
    return templates.TemplateResponse("Event/List/list_event.html",{'request':request,"events":event})

@Root.post("/create_event") #create an event
def creatEvent(request:Request,eventName:str = Form(),eventType:str =Form(...), eventDate: str = Form(),eventAddress:str = Form(),eventDescription: Optional[str] = Form(None),Db:Session = Depends(connecting)):
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
    Db.commit()
    Db.refresh(newEvent)
    return RedirectResponse("/event_list",status_code=303)


@Root.get("/detail/{event_id}/")#la root pour voir un evenement
def eventDetail(request:Request,event_id : str,event:Session = Depends(connecting)):
    getEvent = event.query(Event).filter(Event.id == event_id).first()
    return templates.TemplateResponse("Event/List/detail.html",{'request':request,"event":getEvent})

@Root.get("/edit_event/{event_id}")#la root pour la modification d'un evenement
def editEvent(request:Request,event_id : str,event:Session = Depends(connecting)):
    editEvent = event.query(Event).filter(Event.id == event_id).first()
    return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"event":editEvent})

@Root.post("/edit_event/{event_id}")#la root pour modifier un evenement
def editEvent(request:Request,event_id : str,eventName:str = Form(...),eventType:str = Form(...),eventDate: str = Form(...),eventPlace:str = Form(...),eventDescription: Optional[str] = Form(None),eventState: str = Form(...),db:Session = Depends(connecting)):
    editedEventData = db.query(Event).filter(Event.id == event_id).first()
    try:
        parsed_modified_date = datetime.fromisoformat(eventDate)
        if(parsed_modified_date < datetime.now()):
            return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,"dateError":'La date doit etre superieur a l\'actuelle !!!','event':editedEventData}, status_code=400)
    except (ValueError,TypeError):
        return templates.TemplateResponse("Event/Forms/edit_form.html",{'request':request,'error':'veillez entrer une date correcte','event':editEventData},status_code=400)

    if not editedEventData:
        raise HTTPException(status_code=400,detail="Evenement intouvable")
    editedEventData.name = eventName
    editedEventData.type = eventType
    editedEventData.date = parsed_modified_date
    editedEventData.place = eventPlace
    editedEventData.description = eventDescription
    editedEventData.state = eventState
    db.commit()
    return RedirectResponse("/event_list",status_code=303)

@Root.post("/delete_event/{event_id}")
def deleteEvent(request:Request,event_id:str,db:Session = Depends(connecting)):
    eventToDelete = db.query(Event).filter(Event.id==event_id).first()
    if not eventToDelete:
        raise HTTPException(status_code=404,detail="cette evenement n'existe pas")
    db.delete(eventToDelete)
    db.commit()
    return RedirectResponse("/event_list",status_code=303)
