from fastapi import Request,Depends,APIRouter,HTTPException,Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from db_setting import connecting
from sqlalchemy.orm import selectinload
from models import Guest,Event,Invite
from datetime import datetime
import urllib.parse

Root = APIRouter()
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates


@Root.get("/share_wedding_dashboard/{event_id}",name="share_wedding_dashboard")#la root pour partager le dashboard d'un evenement au couple organisateur
async def shareWeddingDashboard(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(Event).where(Event.id == event_id))
    event = res.scalars().first()
    phone = event.couple_phone_number if event else None
    if not event:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    dashboard_url = f"http://easyinvite-1.onrender.com/wedding_dashboard/{event_id}"
    message = f"Bonjour cher {event.couple_name}, voici le lien pour accéder au tableau de bord de votre événement de '{event.type}': *{dashboard_url}*"
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{phone}?text={encoded_message}"
    return RedirectResponse(url=whatsapp_url)
@Root.get("/wedding_dashboard/{event_id}",name="wedding_dashboard")#la root pour le dashboard d'un evenement
async def getWeddingDashboard(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    year = datetime.now()
    copyright = year.year
    stmnt =(select(Guest).where(Guest.event_id == event_id).options(selectinload(Guest.event),selectinload(Guest.invite).selectinload(Invite.guestResponse)))
    event_res = await db.execute(stmnt)
    events = event_res.scalars().all()
    guest_res = await db.execute(select(func.count()).select_from(Guest).where(Guest.event_id == event_id,Guest.is_present == True))
    total_guest_present =  guest_res.scalar()
    res = await db.execute(select(Event).where(Event.id == event_id))
    event = res.scalars().first()
    if not event:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    total_guest = len(events)
    present_guest = len([guest for guest in events if guest.invite.guestResponse is not None and guest.invite.guestResponse.response == "yes"])
    absent_guest = len([guest for guest in events if guest.invite.guestResponse is not None and guest.invite.guestResponse.response == "no"])
    pending_guest = total_guest - present_guest - absent_guest
    return templates.TemplateResponse("Event/wedding_dashboard/wedding_dashboard.html",{'request':request,'copyright':copyright,'events':events,'event':event,
    'total_guest':total_guest,'total_guest_present':total_guest_present,'present_guest':present_guest,'pending_guest':pending_guest,'absent_guest':absent_guest})

@Root.get("/total_guest/{event_id}",name="wedding_dashboard")#la root pour le total des invites de l'evenement
async def getWeddingDashboard(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(Event).where(Event.id==event_id).options(selectinload(Event.guests)))
    event_res=res.scalars().all()
    result = await db.execute(select(Event).where(Event.id==event_id))
    event = result.scalars().first()
    if not event_res and not event:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    guest_event =event_res[0].guests  if event_res else None
    return templates.TemplateResponse("Event/wedding_dashboard/list/total_guest.html",{'request':request,'event':guest_event,'set_event':event})

@Root.get("/present_guest/{event_id}",name="present_guest")#la root pour les invites qui seront present a l'evenement
async def preset_guest(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(Guest).where(Guest.event_id==event_id).options(selectinload(Guest.event),selectinload(Guest.invite).selectinload(Invite.guestResponse)))
    event_res=res.scalars().all()
    result = await db.execute(select(Event).where(Event.id==event_id))
    event = result.scalars().first()
    if not event_res:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    present_guest = [guest for guest in event_res if guest.invite.guestResponse is not None and guest.invite.guestResponse.response == "yes"]#list des invite qui seront present
    return templates.TemplateResponse("Event/wedding_dashboard/list/present_guest.html",{'request':request,'present_guest':present_guest,'set_event':event})

@Root.get("/absent_guest/{event_id}",name="absent_guest")#la root pour  les invites qui ne seront present a l'evenement
async def absent_guest(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(Guest).where(Guest.event_id==event_id).options(selectinload(Guest.event),selectinload(Guest.invite).selectinload(Invite.guestResponse)))
    event_res=res.scalars().all()
    result = await db.execute(select(Event).where(Event.id==event_id))
    event = result.scalars().first()
    if not event_res:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    absent_guest = [guest for guest in event_res if guest.invite.guestResponse is not None and guest.invite.guestResponse.response == "no"]#list des invite qui ne seront pas present
    return templates.TemplateResponse("Event/wedding_dashboard/list/absent_guest.html",{'request':request,'absent_guest':absent_guest,'set_event':event})

@Root.get("/pending_guest/{event_id}",name="pending_guest")#la root pour  les invites qui ne seront present a l'evenement
async def absent_guest(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(Guest).where(Guest.event_id==event_id).options(selectinload(Guest.event),selectinload(Guest.invite).selectinload(Invite.guestResponse)))
    event_res=res.scalars().all()
    result = await db.execute(select(Event).where(Event.id==event_id))
    event = result.scalars().first()
    if not event_res:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    pending_guest = [guest for guest in event_res if guest.invite.guestResponse is None ]#list des invite qui n'ont pas encore confirmer
    return templates.TemplateResponse("Event/wedding_dashboard/list/pending_guest.html",{'request':request,'pending_guest':pending_guest,'set_event':event})

@Root.get("/guest_present/{event_id}",name="is_present")#la root pour  les invites dont on a deja scanner l'invitation
async def absent_guest(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    res = await db.execute(select(Guest).where(Guest.event_id==event_id,Guest.is_present == True))
    guests=res.scalars().all()
    result = await db.execute(select(Event).where(Event.id==event_id))
    event = result.scalars().first()
    if not guests and not event:
        return templates.TemplateResponse("Event/wedding_dashboard/dashboard_not_available.html",{'request':request})
    return templates.TemplateResponse("Event/wedding_dashboard/list/is_presence_guest.html",{'request':request,'are_present':guests,'set_event':event})

@Root.get("/telephone/{event_id}") #la rechecher d'une donnee
async def searchEvent(request:Request,event_id :str,telephone:str,db:AsyncSession = Depends(connecting)):
    try : 
        telephone
    except ValueError :#=Query(...,max_length = 14,description ="le numero doit contenir au minimum 10 caractere")
        return HTTPException(400,"le numero doit etre egale a 10 au min et a 14 au max")
    get_guest = select(Guest).where(Guest.telephone.like(f"%{telephone}%"),Guest.event_id==event_id)
    res = await db.execute(get_guest)
    guest =res.scalars().all()
    get_event =select(Event).where(Event.id==event_id)#get event
    event_res = await db.execute(get_event)
    event =event_res.scalars().first()
    if not guest :
        raise HTTPException(404,"invite introuvable")
    return templates.TemplateResponse("Guest/List/list.html",{'request':request,"guests":guest,'event':event,'event_id':event_id})
