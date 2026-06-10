from fastapi import APIRouter, Depends, Form, HTTPException,Request,Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse,StreamingResponse,HTMLResponse
from fastapi.templating import Jinja2Templates  
from sqlalchemy import select,desc,func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from db_setting import connecting
import os,io,base64,qrcode
from jinja2 import Environment, FileSystemLoader
from fastapi.responses import StreamingResponse
from models import Ticket_price,Ticket,Event,User,Order
from Routers.invite import get_day, get_month
from datetime import datetime
from config import secret,algo
from jose import jwt
from utils.cryptography.crypt_file import encrypt_token,decrypt_token
from uuid import UUID,uuid4
from Routers.loging import get_curent_user,get_current_user_from_cookie,admin_required
from app.security.permissions import permission_required
from xhtml2pdf import pisa
from Routers.tasks import generer_qr_code_base64
from utils.redis_config import redis_conn
from utils.Qr_Utils.qrCodeUtils import createTicketQrCode

Root = APIRouter(tags =["easyInvite"],dependencies =[Depends(get_current_user_from_cookie),Depends(admin_required)])
templates = Jinja2Templates(directory="Templates")  
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static
# Configuration de Jinja2 pour charger notre template HTML
env = Environment(loader=FileSystemLoader("templates"))
#----------------------------------
async def get_current_seri(event_id:str,db:AsyncSession):#methode pour la composition d'une serie 
    res = await db.execute(select(Ticket).where(Ticket.event_id == event_id).order_by(desc(Ticket.creation)).limit(1))
    ticket = res.scalar_one_or_none()
    current_year = datetime.now().year
    if not ticket or not ticket.seri:
        return f"EI-{current_year}-001"
    try:
        get_recent_seri = ticket.seri
        recent_seri_parts = get_recent_seri.split("-") #prendre l'ancienne serie pour incrementer l'id
        recent_seri = int(recent_seri_parts[-1])
        recent_ticket_year = int(recent_seri_parts[1])
        if recent_ticket_year != current_year:
            return f"EI-{current_year}-001"
        incrementation = recent_seri + 1
        new_serie = f"EI-{current_year}-{incrementation:03d}"
        return new_serie
    except (ValueError,IndexError):
        raise HTTPException(status_code=500,detail="probleme lors de la composition de la serie")

async def get_current_ticket_number(event_id:str,db:AsyncSession):
    res = await db.execute(select(Ticket).where(Ticket.event_id == event_id).order_by(desc(Ticket.creation)).limit(1))
    ticket = res.scalar_one_or_none()
    if not ticket or not ticket.number:
        return 1
    get_recent_number = ticket.number
    new_number = get_recent_number + 1 
    return new_number

def xhtml2pdf_link_callback(uri, rel):
    if uri.startswith("data:image"):
        return uri
        
    # On construit le chemin absolu
    path = os.path.join(os.getcwd(), uri)
    
    # PETIT TEST DE SÉCURITÉ : Est-ce que le fichier existe vraiment ?
    if not os.path.exists(path):
        print(f"⚠️ ERREUR CRITIQUE : Fichier introuvable à l'emplacement : {path}")
    else:
        print(f"✅ SUCCÈS : L'image a été trouvée ici : {path}")
        
    return path

def get_base64_bg_image():
    import base64
    # On construit le chemin propre vers l'image
    img_path = os.path.join(os.getcwd(), "static", "Pictures", "bg-gold.png")
    try:
        with open(img_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded_string}"
    except Exception as e:
        print(f"⚠️ Impossible de charger l'image de fond : {e}")
        return ""
#----------------------

#scan du ticket
@Root.get("/scan-ticket")
async def scan_ticket(ticket_id: str, db: AsyncSession = Depends(connecting)):
    # 1. Tu cherches le billet
    result = await db.execute(select(Ticket).where(Ticket.qr_token == ticket_id))
    ticket = result.scalar_one_or_none()
    
    # Si le billet n'existe pas en base :
    if ticket is None:
        return {"valid": False, "message": "Billet introuvable"}
        
    # Si le billet a déjà été scanné par le passé :
    if ticket.is_scanned:
        return {"valid": False, "message": "Billet déjà validé"}
        
    # Si tout est bon, on le valide
    ticket.is_scanned = True
    await db.commit()
    
    return {"valid": True, "name": ticket.participator_name, "ticket_id": ticket.id}

@Root.get("/ticket/view/{ticket_id}")#ticket detail
async def get_ticket_info(request:Request,ticket_id:str,access_token = Cookie(None),db:AsyncSession=Depends(connecting),user= Depends(permission_required("view_ticket"))):
    current_res = jwt.decode(access_token,secret,algorithms = [algo])
    user_id = current_res.get("user")
    if user_id:
        user_res = await db.execute(select(User).where(User.id ==user_id).options().options(selectinload(User.roles),selectinload(User.groups)))
        user = user_res.scalars().first()
        for role in user.roles:
             user_role = role.name    
    ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.orders)))
    ticket = ticket_res.scalars().first()
    if not ticket : 
        raise HTTPException(status_code=404,detail="aucun ticket trouvee")
    event_id = ticket.event_id
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    if not event : 
        raise HTTPException(status_code=404,detail="aucun evenmement correspondant")
    return templates.TemplateResponse("ticket/list/detail.html",{'request':request,'ticket':ticket,'event':event,'current_user_role':user_role})

@Root.get("/ticket/participator_number/{event_id}")
async def search_participator_ticket_phone(request:Request,participator_phone:str,event_id:str,access_token: str = Cookie(None),db:AsyncSession = Depends(connecting),user= Depends(permission_required("view_ticket"))):
    if not access_token:
        return RedirectResponse("/login") # Rediriger si non connecté
    current_res = jwt.decode(access_token, secret, algorithms=[algo])
    user_id = current_res.get("user")
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    user = user_res.scalars().first()
    user_role = user.roles[0].name if user and user.roles else "guest"
    #-------------------------------        
    from sqlalchemy import or_

    res = select(Ticket).options(selectinload(Ticket.orders)).join(Ticket.orders).where(
    Order.event_id == event_id,
    or_(
        Order.buyer_number.like(f"%{participator_phone}%"),
        Ticket.participator_number.like(f"%{participator_phone}%")
    )
).distinct()
    result = await db.execute(res)
    tickets = result.scalars().all()
    deleting =request.session.pop("success_deleting",None)
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalars().first()
    if not event :
        raise  HTTPException(status_code=404,detail="event not found")
    return templates.TemplateResponse("ticket/list/list_tickets.html", {
        'request': request,
        'deleting_message':deleting,
        'event': event, 
        'current_user_role': user_role,
        'tickets':tickets
    })

@Root.get("/list_tickets/{event_id}",name="ticket_list") #get the ticket list
async def get_ticket_list(request:Request,event_id:str,page:int = 1,access_token = Cookie(None),db:AsyncSession = Depends(connecting),user= Depends(permission_required("view_ticket"))):
    current_res = jwt.decode(access_token,secret,algorithms = [algo])
    user_id = current_res.get("user")
    if user_id:
        user_res = await db.execute(select(User).where(User.id ==user_id).options().options(selectinload(User.roles),selectinload(User.groups)))
        user = user_res.scalars().first()
        for role in user.roles:
             user_role = role.name
    event_res = await db.execute(select(Event).where(Event.id==event_id))
    event = event_res.scalars().first()
    total_ticket = (await db.execute(select(func.count()).select_from(Ticket))).scalar() or 0
    total_scanned_tickets = (await db.execute(select(func.count()).select_from(Ticket).where(Ticket.is_scanned==True))).scalar() or 0
    total_unscanned_tickets = (await db.execute(select(func.count()).select_from(Ticket).where(Ticket.is_scanned==False))).scalar() or 0
    deleting =request.session.pop("success_deleting",None)
    #-----------------------pagination
    per_page = 50 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_pages = (total_ticket + per_page - 1) // per_page #le nombre total de page
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
    if not event :
        raise HTTPException(404,"aucun evenement trouvé")
    edit_ticket_message= request.session.pop('edit_ticket_message',None)
    return templates.TemplateResponse("ticket/list/list_tickets.html",{'request':request,
    'total_ticket':total_ticket,'total_scanned_tickets':total_scanned_tickets,
    'total_unscanned_tickets':total_unscanned_tickets,'deleting_message':deleting,'event':event,
    'current_user_role':user_role,'tickets':tickets,
    'edit_ticket_message':edit_ticket_message,
    'total_pages': total_pages,
    'page': page,
    },status_code=303)

@Root.get("/ticket/qr/{qr_token}")#pour l'image du qr_code sur le billet
async def get_qr_img(qr_token:str):
    qr_image = createTicketQrCode(qr_token)
    return StreamingResponse(qr_image,media_type = "image/png") 

@Root.get("/ticket/{event_id}") 
async def get_paiement_view(request:Request,event_id:str):
    success_message = request.session.pop("success_message",None)
    return templates.TemplateResponse("ticket/forms/form.html",{'request':request,'success':success_message,'event_id':event_id})

@Root.post("/submit_ticket/{event_id}")
async def get_submitted_form(request:Request,event_id:str ,ticket_type:str = Form(...),price:str=Form(...),device:str = Form(...),db:AsyncSession = Depends(connecting)):
    converted_price = float(price)
    ticket_res = await db.execute(select(Ticket_price).where(Ticket_price.event_id==event_id,Ticket_price.ticket_type == ticket_type))
    ticket = ticket_res.scalars().first()
    message = None
    if ticket:
        message = "ce ticket existe deja"
        return templates.TemplateResponse("ticket/forms/form.html",{'request':request,'message':message,'event_id':event_id})    
    new_ticket = Ticket_price(
        event_id=event_id,
        ticket_type = ticket_type,
        price = converted_price,
        device =device
    )
    db.add(new_ticket)
    try:
        await db.commit()
        await db.refresh(new_ticket)
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500,detail="erreur lors de l'enregistrement")
    request.session['success_message'] = "ticket enregistre avec succees"
    return RedirectResponse(url=f"/ticket/{event_id}",status_code=303)

#-------------------------downloading
async def generate_ticket_pdf_in_memory(ticket_id:str,order_id: str, db: AsyncSession) -> io.BytesIO:#telechargement d'un seul billet
    # 1. Récupération de la commande et de l'événement lié
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.events))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Commande introuvable.")

    # 2. Récupération de TOUS les tickets associés à cette commande
    result_tickets = await db.execute(select(Ticket).where(Ticket.order_id == order_id,Ticket.id == ticket_id))
    ticket = result_tickets.scalars().first()
    
    if not ticket:
        raise ValueError("Aucun ticket trouvé pour cette commande.")

    # 3. Génération des QR codes uniques pour CHAQUE ticket
    # On utilise le token unique propre à chaque ticket en BDD
    qr_base64 = generer_qr_code_base64(ticket.qr_token)
    # On crée dynamiquement l'attribut que le HTML va lire dans la boucle
    ticket.qr_code_base64 = f"data:image/png;base64,{qr_base64}"

    # 4. Rendu du template global avec la liste complète
    template = env.get_template("Invitation/show_invite/other/pdf_ticket.html")
    html_content = template.render(
        bg_image_base64=get_base64_bg_image(),
        ticket=ticket,  # 🔥 On passe la liste complète ici
        event_name=order.events.name if order.events else "Événement",
        event_date=order.events.date.date() if order.events and order.events.date else "Date inconnue",
        event_time=order.events.date.time() if order.events and order.events.date else "00:00",
        event_location=order.events.location if order.events else "Lieu inconnu",
        event_address=order.events.address if order.events else "",
        ticket_type=order.ticket_type
    )
    
    # 5. Compilation par xhtml2pdf (pisa)
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        io.StringIO(html_content), 
        dest=pdf_buffer,
        link_callback=xhtml2pdf_link_callback
    )
    
    if pisa_status.err:
        raise RuntimeError(f"Échec de la compilation PDF via xhtml2pdf: {pisa_status.err}")
        
    pdf_buffer.seek(0)
    return pdf_buffer

async def generate_order_pdf_in_memory(order_id: str, db: AsyncSession) -> io.BytesIO:#telechargement de tout les billets
    # 1. Récupération de la commande et de l'événement lié
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.events))
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ValueError("Commande introuvable.")

    # 2. Récupération de TOUS les tickets associés à cette commande
    result_tickets = await db.execute(select(Ticket).where(Ticket.order_id == order_id))
    tickets = result_tickets.scalars().all()
    
    if not tickets:
        raise ValueError("Aucun ticket trouvé pour cette commande.")

    # 3. Génération des QR codes uniques pour CHAQUE ticket
    for ticket in tickets:
        # On utilise le token unique propre à chaque ticket en BDD
        qr_base64 = generer_qr_code_base64(ticket.qr_token)
        # On crée dynamiquement l'attribut que le HTML va lire dans la boucle
        ticket.qr_code_base64 = f"data:image/png;base64,{qr_base64}"

    # 4. Rendu du template global avec la liste complète
    template = env.get_template("Invitation/show_invite/other/pdf_ticket.html")
    html_content = template.render(
        bg_image_base64=get_base64_bg_image(),
        tickets=tickets,  # 🔥 On passe la liste complète ici
        event_name=order.events.name if order.events else "Événement",
        event_date=order.events.date.date() if order.events and order.events.date else "Date inconnue",
        event_time=order.events.date.time() if order.events and order.events.date else "00:00",
        event_location=order.events.location if order.events else "Lieu inconnu",
        event_address=order.events.address if order.events else "",
        ticket_type=order.ticket_type
    )
    
    # 5. Compilation par xhtml2pdf (pisa)
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(
        io.StringIO(html_content), 
        dest=pdf_buffer,
        link_callback=xhtml2pdf_link_callback
    )
    
    if pisa_status.err:
        raise RuntimeError(f"Échec de la compilation PDF via xhtml2pdf: {pisa_status.err}")
        
    pdf_buffer.seek(0)
    return pdf_buffer




#---------------------------------methodes
@Root.get("/create/{event_id}/ticket")#chargement du formulaire de la creatio de ticket
async def get_ticket_form(request:Request,event_id:str,db:AsyncSession = Depends(connecting),user= Depends(permission_required("create_ticket"))):
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    ticket_res = await db.execute(select(Ticket_price).where(Ticket_price.event_id==event_id))
    tickets = ticket_res.scalars().all()
    creation_message= request.session.pop('creation_message',None)
    return templates.TemplateResponse('ticket/forms/register.html',{'request':request,'event':event,'tickets':tickets,'creation_message':creation_message})

@Root.post("/create/ticket")#route pour la creation d'un ticket
async def submit_ticket_form(request:Request,event_id:str = Form(...),buyer_name:str = Form(...),buyer_phone:str = Form(...),ticket_type:str = Form(...),db:AsyncSession = Depends(connecting),user= Depends(permission_required("create_ticket"))):
    res = await db.execute(select(Event).where(Event.id == event_id))
    event = res.scalars().first()
    if not event:
        raise HTTPException(status_code = 404,detail="evenement introuvable")
    str_get_pass = str(uuid4())[:8]
    ticket_seri =await get_current_seri(event_id,db)
    ticket_number =await get_current_ticket_number(event_id,db)
    new_ticket = Ticket (
        event_id=event_id,
        type=ticket_type,
        seri=ticket_seri,
        number= ticket_number,
        participator_name=buyer_name,
        qr_token = str(uuid4()),
        get_pass=str_get_pass
    )
    try:
        db.add(new_ticket)
        await db.commit()
        await db.refresh(new_ticket)
    except:
        db.rollback()
        raise HTTPException(status_code=500,detail="erreur lors d'enregistrement")
    request.session['creation_message'] = "billet crée avec succé"
    return RedirectResponse(f"/create/{event_id}/ticket",303)
@Root.get("/edit/ticket/{event_id}/{ticket_id}")
async def get_ticket_form(request:Request,event_id:str,ticket_id:str,db:AsyncSession = Depends(connecting),user= Depends(permission_required("edit_ticket"))):
    ticket_res = await db.execute(select(Ticket).where(Ticket.id == ticket_id).options(selectinload(Ticket.orders)))
    ticket = ticket_res.scalars().first()
    res = await db.execute(select(Ticket_price).where(Ticket_price.event_id==event_id))
    ticket_prices = res.scalars().all()
    
    return templates.TemplateResponse('ticket/forms/edit_ticket.html',{'request':request,'event_id':event_id,'ticket':ticket,'ticket_prices':ticket_prices})

@Root.post("/edit/ticket")
async def submit_ticket_form(request:Request,ticket_id:UUID = Form(...),order_id:str = Form(None),event_id:str = Form(...),buyer_name:str = Form(...),buyer_phone:str = Form(None),ticket_type:str = Form(...),db:AsyncSession = Depends(connecting),user= Depends(permission_required("view_ticket"))):
    strint_ticket_id = str(ticket_id)
    res = await db.execute(select(Event).where(Event.id == event_id))
    event = res.scalars().first()
    if not event:
        raise HTTPException(status_code = 404,detail="evenement introuvable")
    ticket_res = await db.execute(select(Ticket).where(Ticket.id == strint_ticket_id))
    ticket = ticket_res.scalars().first()
    if not ticket:
        raise HTTPException(status_code = 404,detail="ticket introuvable")
    str_get_pass = str(uuid4())[:8]
    ticket_seri =await get_current_seri(event_id,db)
    ticket_number =await get_current_ticket_number(event_id,db)
    ticket.event_id=event_id
    ticket.order_id=order_id if ticket.order_id else None
    ticket.type=ticket_type
    ticket.seri=ticket_seri
    #ticket.number= ticket_number
    ticket.participator_name=buyer_name
    ticket.qr_token = str(uuid4())
    ticket.get_pass=str_get_pass
    try:
        await db.commit()
    except:
        db.rollback()
        raise HTTPException(status_code=500,detail="erreur lors d'enregistrement")
    request.session['edit_ticket_message'] = "billet modifié avec succé"
    return RedirectResponse(f"/list_tickets/{event_id}",303)

from app.security.permissions import  permission_required
@Root.post("/delete_ticket/{ticket_id}")
async def delete_ticket(request: Request, ticket_id: str,event_id:str = Form(...), user=Depends(permission_required("delete_ticket")), db: AsyncSession = Depends(connecting)):
    res = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket_to_delete = res.scalars().first()
    if not ticket_to_delete:
        raise HTTPException(status_code=404, detail="Ce ticket n'existe pas")
    try:
        await db.delete(ticket_to_delete)
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(f"-Erreur-------------------------------{e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
    request.session["success_deleting"] = "🎉 Tiquet supprimée avec succès !"
    
    # Rediriger vers la liste des commandes de l'événement
    return RedirectResponse(f"/list_tickets/{event_id}", status_code=303)