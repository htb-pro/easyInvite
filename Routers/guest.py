#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter,Query,Cookie,Response
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select,and_,func,desc
from uuid import uuid4
from db_setting import engine,connecting
from sqlalchemy.orm import Session,selectinload
from sqlalchemy.exc import IntegrityError
from models import *
from typing import Optional
from datetime import datetime
import os
from pathlib import Path
from utils.Qr_Utils.qrCodeUtils import createInviteQrCode
import base64,urllib.parse
from Routers.loging import get_current_user_from_cookie
from app.security.permissions import permission_required
from urllib.parse import quote
from jose import jwt 
from config import secret,algo

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates

#--------------------About guest
@Root.get("/guest_list/{event_id}",name="guest_list") #get the guest list
async def get_guest_list(request:Request,event_id:str,access_token = Cookie(None),db:AsyncSession = Depends(connecting)):
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
    #variable contenant message whatsapp
    
    if not event :
        raise HTTPException(404,"aucun evenement trouvé")
    if not guests :
        return templates.TemplateResponse("Guest/List/notFound.html",{'request':request,"Error":'404','event':event})
    return templates.TemplateResponse("Guest/List/list.html",{'request':request,'invite':invite,'event':event,'guests':guests,'event_id':event_id,'present_guest':present_guest,'absent_guest':absent_guest,'current_user_role':user_role},status_code=303)

@Root.get("/share_invite/{event_id}/{guest_id}")
async def send_whatsapp_redirect(event_id: str,guest_id: str, db: AsyncSession = Depends(connecting)):
    # 1. Récupérer l'invité en BDD
    guest_res = await db.execute(select(Guest).where(Guest.id == guest_id,Guest.event_id == event_id))
    guest = guest_res.scalars().first()
     
    if not guest:
        raise HTTPException(status_code=404, detail="Invité non trouvé")

    # 2. Préparer les données
    guest_get_pass = guest.get_pass
    invite_url = f"http://easyinvite-1.onrender.com/invite/{event_id}/{guest_id}/create"
    message = f"INVITATION OFFICIELLE\n\nBonjour {guest.name}, vous êtes invité à notre événement.\n\n voici votre jeton d'accès en cas de manque du qr code *{guest_get_pass}* \n\n cliquez sur le lien pour voir et télecharger votre invitation . \n\n*Note : si le lien n'est pas cliquable veillez enregistrer ce numero dans vos contacts ou s'implement repondre a ce message.* \n\nlien:{invite_url}"

    
    # 3. Nettoyer le numéro (ne garder que les chiffres)
    # On suppose que le numéro est stocké avec l'indicatif pays (ex: 243...)
    clean_phone = "".join(filter(str.isdigit, guest.telephone))
    # 4. Encoder le message pour l'URL
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"
    
    # 5. Rediriger l'utilisateur directement vers WhatsApp
    return RedirectResponse(url=whatsapp_url)
    #---------

@Root.get("/telephone/{event_id}") #la rechecher d'une donnee
async def searchEvent(request:Request,event_id :str,telephone:str = None,db:AsyncSession = Depends(connecting)):
    query =select(Guest).where(Guest.event_id==event_id)
    if telephone:
        query = query.where(Guest.telephone.like(f"%{telephone}%"))
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

@Root.get("/create/{event_id}/guest",name="guestForm") #get the guest register form
async def get_invited(request:Request,event_id:str,success:int | None = None,db:AsyncSession = Depends(connecting),
                      user : User = Depends(permission_required("create_guest"))):
    select_event=select(Event).options(selectinload(Event.guests)).where(Event.id == event_id)#recuperer l'evenement en fin d'y associer l'invite
    result= await  db.execute(select_event)
    event=result.scalars().first() 
    get_success = success ==1
    form_data = request.session.pop('form_data',{})
    return templates.TemplateResponse("Guest/Forms/form.html",{'request':request,'event':event,'success':get_success,**form_data})

@Root.post('/create/{event_id}/guest')#get the guest register 
async def newGuest(request:Request,event_id:str,guestName:str=Form(),guestType:str=Form(None),guestPlace:str = Form(None),
                   guestTel:str=Form(),user=Depends(permission_required("create_guest")),db:AsyncSession = Depends(connecting)):
    select_event = (select(Event).where(Event.id==event_id).options(selectinload(Event.guests)))
    get_event = await db.execute(select_event)
    event = get_event.first()
    select_guest_tel =select(Guest).where(and_(Guest.telephone == guestTel,Guest.event_id == event_id))#verifier si le guest existe deja avec le meme numero ou email
    tel_res = await db.execute(select_guest_tel)
    select_guest_mail =select(Guest).where(and_(Guest.event_id == event_id))#verifier si le guest existe deja avec le meme email
    email_res = await db.execute(select_guest_mail)
    is_guest_tel =tel_res.scalars().first()
    is_guest_email = email_res.scalars().first()
    error_message = ""
    guest_get_pass = str(uuid4())[:8]
    def set_data(message):
         request.session['form_data'] = {
                     'uniqueValueError':message, 
                     'guestName':guestName,
                     'guestType':guestType,
                     'guestPlace':guestPlace, 
                     'guestTel':guestTel,
                }
    if not event :
        raise HTTPException(status_code=404,detail="Evenement introuvable")
    if is_guest_tel : #si un invite existe avec le numero entrer 
                error_message = 'un invité existe deja avec ce numero telephonique'
                set_data(error_message)
                return RedirectResponse(f'/create/{event_id}/guest',status_code=303)#renvoi erreur
    # if is_guest_email : 
    #             error_message = 'un invité existe deja avec cet email'
    #             set_data(error_message)
    #             return RedirectResponse(f'/create/{event_id}/guest',status_code=303)#renvoi erreur
    
    guest = Guest(
        name = guestName,
        guest_type = guestType,
        place = guestPlace,
        telephone = guestTel,
        event_id = event_id,
        qr_token = str(uuid4()),
        get_pass = guest_get_pass,
    ) 
    db.add(guest)
    await db.commit()
    await db.refresh(guest)
    new_invite = Invite(
    qr_token = str(uuid4()),
    guest_id = guest.id
    )
    db.add(new_invite)
    await db.commit()
    await db.refresh(guest)     
    await db.refresh(new_invite)     
    return RedirectResponse(url=f'/create/{event_id}/guest?success=1',status_code=303)#"success":success

@Root.get("/edit_guest_form/{event_id}/{guest_id}")
async def editGuest(request:Request,event_id:str,guest_id: str,user=Depends(permission_required("edit_guest")),db:AsyncSession=Depends(connecting)):
    get_guest = select(Guest).where(Guest.id ==guest_id,Guest.event_id == event_id).options(selectinload(Guest.invite))
    result = await db.execute(get_guest)
    guest = result.scalars().first()
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    if not guest :
        raise HTTPException(404,"invité non touve")
    return templates.TemplateResponse("Guest/Forms/edit_form.html",{'request':request,"guest":guest,'event':event},status_code=303)

@Root.post("/edit_guest_form/{Event_id}")#edit guest form
async def editGuestPost(request:Request,Event_id:str,guest_id:str = Form(...),guestName:str=Form(...),guestType:str=Form(...),guestPlace : str = Form(...),
                        guestState : int = Form(...),guestTel:str=Form(),
                        user=Depends(permission_required("edit_guest")),db:AsyncSession = Depends(connecting)):
    get_new_guest = select(Guest).where(Guest.id ==guest_id,Guest.event_id == Event_id).options(selectinload(Guest.invite)) #prepare le guest
    result = await db.execute(get_new_guest) #select le guest concerné
    new_guest = result.scalars().first()#recupere le guest concerné
    if not new_guest:
        raise HTTPException (status_code = 404,detail = "Invite introuvable")
    new_guest.name = guestName
    new_guest.guest_type = guestType
    new_guest.place = guestPlace
    new_guest.is_present = bool(guestState)
    new_guest.telephone = guestTel
    try:
        await db.commit()
    except IntegrityError:
        db.rollback()
        return templates.TemplateResponse('Guest/Forms/form.html',{'request':request,'event':new_guest,'emailError':'un invité existe deja avec cet email', 'guestName':guestName, 'guestType':guestType, 'guestPlace':guestPlace,'guestTel':guestTel, 'guestEmail':guestEmail},status_code=400)
    return RedirectResponse(f"/guest_list/{Event_id}",status_code=303)

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

