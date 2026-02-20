#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,Query
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_
from uuid import uuid4
import models
from db_setting import engine,connecting
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.exc import IntegrityError
from models import *
from datetime import date
from typing import Optional
from datetime import datetime,date
import os
from pathlib import Path
from utils.Qr_Utils.qrCodeUtils import createInviteQrCode
import base64

Root = APIRouter()
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates

#--------------------About guest
@Root.get("/guest_list/{event_id}",name="guest_list") #get the guest list
async def get_guest_list(request:Request,event_id:str,db:AsyncSession = Depends(connecting)):
    get_event_guest = select(Event).options(selectinload(Event.guests)).where(Event.id == event_id)#prendre l'evenement qui a des invites
    result = await db.execute(get_event_guest)
    event = result.scalars().first()
    guests = list(event.guests) if event else []
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
    if not event :
        raise HTTPException(404,"aucun evenement trouvé")
    if not guests :
        return templates.TemplateResponse("Guest/List/notFound.html",{'request':request,"Error":'404','event':event})
    return templates.TemplateResponse("Guest/List/list.html",{'request':request,'invite':invite,'event':event,'guests':guests,'event_id':event_id,'present_guest':present_guest,'absent_guest':absent_guest},status_code=303)

@Root.get("/telephone/{event_id}") #la rechecher d'une donnee
async def searchEvent(request:Request,event_id :str,telephone:str=Query(...,max_length = 14,description ="le numero doit contenir au minimum 10 caractere"),db:AsyncSession = Depends(connecting)):
    try : 
        telephone
    except ValueError :
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

@Root.get('/guest/{guest_id}/{event_id}/detail')#detail endpoint
async def guestDetail(request:Request,guest_id:str,event_id:str,db:AsyncSession = Depends(connecting)):
    get_guest =select(Guest).where(Guest.id ==guest_id,Guest.event_id == event_id)
    result = await db.execute(get_guest)
    guest =result.scalars().first()
    if not guest :
        raise HTTPException(404,"invite non trouvé")
    return templates.TemplateResponse("Guest/List/detail.html",{'request':request,"guest":guest,"event_id":event_id},status_code=303)

@Root.get("/create/{event_id}/guest",name="guestForm") #get the guest register form
async def get_invited(request:Request,event_id:str,success:int | None = None,db:AsyncSession = Depends(connecting)):
    select_event=select(Event).options(selectinload(Event.guests)).where(Event.id == event_id)#recuperer l'evenement en fin d'y associer l'invite
    result= await  db.execute(select_event)
    event=result.scalars().first() 
    get_success = success ==1
    form_data = request.session.pop('form_data',{})
    return templates.TemplateResponse("Guest/Forms/form.html",{'request':request,'event':event,'success':get_success,**form_data})

@Root.post('/create/{event_id}/guest')#get the guest register 
async def newGuest(request:Request,event_id:str,guestName:str=Form(),guestType:str=Form(),guestPlace:str = Form(...),
                   guestTel:str=Form(),guestEmail:Optional[str]=Form(None),db:AsyncSession = Depends(connecting)):
    select_event = (select(Event).where(Event.id==event_id).options(selectinload(Event.guests)))
    get_event = await db.execute(select_event)
    event = get_event.first()
    select_guest_tel =select(Guest).where(and_(Guest.telephone == guestTel,Guest.event_id == event_id))#verifier si le guest existe deja avec le meme numero ou email
    tel_res = await db.execute(select_guest_tel)
    select_guest_mail =select(Guest).where(and_(Guest.email == guestEmail,Guest.event_id == event_id))#verifier si le guest existe deja avec le meme email
    email_res = await db.execute(select_guest_mail)
    is_guest_tel =tel_res.scalars().first()
    is_guest_email = email_res.scalars().first()
    error_message = ""
    def set_data(message):
         request.session['form_data'] = {
                     'uniqueValueError':message, 
                     'guestName':guestName,
                     'guestType':guestType,
                     'guestPlace':guestPlace, 
                     'guestTel':guestTel,
                     'guestEmail':guestEmail
                }
    if not event :
        raise HTTPException(status_code=404,detail="Evenement introuvable")
    if is_guest_tel : #si un invite existe avec le numero entrer 
                error_message = 'un invité existe deja avec ce numero telephonique'
                set_data(error_message)
                return RedirectResponse(f'/create/{event_id}/guest',status_code=303)#renvoi erreur
    if is_guest_email : 
                error_message = 'un invité existe deja avec cet email'
                set_data(error_message)
                return RedirectResponse(f'/create/{event_id}/guest',status_code=303)#renvoi erreur
    new_invite = Invite(
    event_id = event_id,
    qr_token = str(uuid4())
    )
    db.add(new_invite)
    guest = Guest(
        name = guestName,
        guest_type = guestType,
        place = guestPlace,
        telephone = guestTel,
        email = guestEmail,
        event_id = event_id,
        qr_token = str(uuid4()),
        invite = new_invite
    ) 
    db.add(guest)
    await db.commit()
    await db.refresh(guest)     
    await db.refresh(new_invite)     
    return RedirectResponse(url=f'/create/{event_id}/guest?success=1',status_code=303)#"success":success

@Root.get("/edit_guest_form/{event_id}/{guest_id}")
async def editGuest(request:Request,event_id:str,guest_id: str,db:AsyncSession=Depends(connecting)):
    get_guest = select(Guest).where(Guest.id ==guest_id,Guest.event_id == event_id)
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    if not guest :
        raise HTTPException(404,"invité non touve")
    return templates.TemplateResponse("Guest/Forms/edit_form.html",{'request':request,"guest":guest,'event_id':event_id},status_code=303)

@Root.post("/edit_guest_form/{Event_id}")#edit guest form
async def editGuestPost(request:Request,Event_id:str,guest_id:str = Form(...),guestName:str=Form(),guestType:str=Form(...),guestPlace : str = Form(...),
                        guestState : int = Form(...),guestTel:str=Form(),guestEmail:Optional[str]=Form(None),db:AsyncSession = Depends(connecting)):
    get_new_guest = select(Guest).where(Guest.id ==guest_id,Guest.event_id == Event_id) #prepare le guest
    result = await db.execute(get_new_guest) #select le guest concerné
    new_guest = result.scalars().first()#recupere le guest concerné
    if not new_guest:
        raise HTTPException (status_code = 404,detail = "Invite introuvable")
    new_guest.name = guestName
    new_guest.guest_type = guestType
    new_guest.place = guestPlace
    new_guest.is_present = bool(guestState)
    new_guest.telephone = guestTel
    new_guest.email = guestEmail
    try:
        await db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse('Guest/Forms/form.html',{'request':request,'event':new_guest,'emailError':'un invité existe deja avec cet email', 'guestName':guestName, 'guestType':guestType, 'guestPlace':guestPlace,'guestTel':guestTel, 'guestEmail':guestEmail},status_code=400)
    return RedirectResponse(f"/guest_list/{Event_id}",status_code=303)

@Root.post('/delete_guest/{event_id}/guest')#root for deleting guest
async def deleteGuest(request:Request,event_id:str,guest_id:str=Form(...),db:AsyncSession=Depends(connecting)):
    get_guest_to_be_deleted = (select(Guest).where(Guest.id==guest_id,Guest.event_id == event_id).options(selectinload(Guest.invite)))
    result = await db.execute(get_guest_to_be_deleted)
    guest_to_be_deleted = result.scalars().first()
    invite = guest_to_be_deleted.invite
    invite_token = guest_to_be_deleted.invite.qr_token
    Guest_name = guest_to_be_deleted.name
    Guest_tel = guest_to_be_deleted.telephone
    if not guest_to_be_deleted: #si le guest n'existe pas dans l'evenement
        raise HTTPException(status_code = 404,detail="invité introuvable")
    await db.delete(guest_to_be_deleted)#suppresion du guest
    await db.commit()#application de modification dans la db
    return RedirectResponse(f"/guest_list/{event_id}",status_code=303)

