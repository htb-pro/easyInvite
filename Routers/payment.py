from fastapi import APIRouter, Depends, Form, HTTPException,Request,status
from fastapi.responses import RedirectResponse,HTMLResponse
from fastapi.templating import Jinja2Templates  
from sqlalchemy import select,func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from db_setting import connecting
from models import Event,Order,Ticket_price,Ticket,ExternalUser
from Routers.invite import get_day
from fastapi_csrf_protect import CsrfProtect
from jose import jwt 
from config import secret,algo,csrf_key,verify_csrf,set_secure_cookie
import secrets,hmac
from itsdangerous import URLSafeTimedSerializer, BadSignature
from Routers.guest import format_to_drc_phone

Root = APIRouter()
templates = Jinja2Templates(directory="Templates")  



@Root.get("/payments/{event_id}")
async def get_paiement_view(request:Request, event_id: str,db:AsyncSession = Depends(connecting)):
    csrf_token = secrets.token_urlsafe(32)
    event = (await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices)))).scalars().first()
    invalid_number = request.session.pop('invalid_number',None)
    # 2. On compte combien de billets ont déjà été vendus
    tickets_sold = await db.scalar(
        select(func.count(Ticket.id)).where(Ticket.event_id == event_id)
    ) or 0
    
    # 3. ON CALCULE LES PLACES RESTANTES 📊
    remaining_place = event.total_capacity - tickets_sold
    
    # Si jamais le calcul donne un chiffre négatif par accident, on le remet à 0
    if remaining_place < 0:
        remaining_place = 0
    response = templates.TemplateResponse(
        "order/forms/order_form.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "event_id": event_id,
            'event':event,
            "show_modal": True,  # Un petit drapeau pour dire au JS d'ouvrir la modal
            'invalid_phone_number':invalid_number,
            'remaining_place':remaining_place
        }
    )

    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,        # Protection contre le vol de jeton par JS (Garder obligatoire)
        samesite="lax",       # Permet au cookie de transiter sur les navigations standards
        secure=set_secure_cookie,         # TRÈS IMPORTANT en local (False permet au cookie de passer sans HTTPS)
        path="/"
        
    )

    return response

@Root.get("/success",name="success")
async def get_success_message(request:Request):
    transaction_id = request.session.pop("code",None)
    return templates.TemplateResponse("order/message/success.html",{'request':request,'transaction_id':transaction_id})

# 1. Tu prépares le décodeur avec ta clé secrète
serializer = URLSafeTimedSerializer(csrf_key)
@Root.post("/make_order/{event_id}")
async def get_paiement_data(
    request: Request, 
    event_id: str, 
    buyer_name: str = Form(...), 
    buyer_phone: str = Form(...),  
    ticket_type: str = Form(...), 
    quantity: int = Form(...),
    transaction_id: str = Form(...),
    _=Depends(verify_csrf),
    db: AsyncSession = Depends(connecting)
):
    converted_transaction_id = transaction_id.lower().strip()
    
    # Nettoyage et uniformisation immédiate du numéro de téléphone
    clean_phone = format_to_drc_phone(buyer_phone)
    print(f"-------------------------Numéro de téléphone nettoyé : {clean_phone}")
    if not clean_phone:
        request.session['invalid_number'] = "Format du numéro de téléphone invalide"
        return RedirectResponse(f"/payments/{event_id}", status_code=303)
        
    if clean_phone.startswith("0"):
        clean_phone = "243" + clean_phone[1:]

    # 🌟 AJOUT : Essayer de récupérer l'ID utilisateur si connecté
    session_user_id = request.cookies.get("session_user_id")
    order_id = None  # On initialise pour le récupérer plus tard

    async with db.begin():
        # 1. On récupère et verrouille l'événement contre la concurrence
        event_result = await db.execute(
            select(Event).where(Event.id == event_id).with_for_update()
        )
        event = event_result.scalar_one_or_none() 
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
            
        # 2. Correction Filtre Prix : On lie le type de billet à cet événement précis
        ticket_res = await db.execute(
            select(Ticket_price).where(Ticket_price.ticket_type == ticket_type, Ticket_price.event_id == event_id)
        )
        ticket = ticket_res.scalars().first()
        if not ticket:
            raise HTTPException(status_code=404, detail="Type de ticket introuvable pour cet événement")

        # 3. Vérification si la transaction existe déjà
        order_res = await db.execute(
            select(Order).where(Order.transaction_id == converted_transaction_id, Order.event_id == event_id)
        )
        order = order_res.scalars().first()
        
        # Comptage global des billets déjà vendus
        tickets_sold = await db.scalar(
            select(func.count(Ticket.id)).where(Ticket.event_id == event_id)
        ) or 0
        remaining_place = max(0, event.total_capacity - tickets_sold)

        if order: 
            csrf_token = secrets.token_urlsafe(32)
            res = await db.execute(select(Ticket_price).where(Ticket_price.event_id == event_id))
            tickets = res.scalars().all()
            
            event_with_prices = (await db.execute(
                select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices))
            )).scalars().first()
            
            exist_message = "Ce code de transaction a déjà été utilisé. Veuillez vérifier ou contacter le support."
            return templates.TemplateResponse(
                "order/forms/order_form.html",
                {
                    'request': request, "csrf_token": csrf_token, 'event': event_with_prices, 
                    'tickets': tickets, 'exist_message': exist_message, 'buyer_name': buyer_name, 
                    'buyer_phone': buyer_phone, 'ticket_type': ticket_type, 'quantity': quantity, 
                    'transaction_id': transaction_id, 'remaining_place': remaining_place
                }
            )

        # 4. Correction Contrôle Capacité
        if tickets_sold + quantity > event.total_capacity: 
            insuffisant_place_message = "Désolé, cet événement est complet ! Plus aucune place n'est disponible."
            
            event_with_prices = (await db.execute(
                select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices))
            )).scalars().first()
            
            res_tickets = await db.execute(select(Ticket_price).where(Ticket_price.event_id == event_id))
            tickets = res_tickets.scalars().all()
            csrf_token = request.cookies.get("fastapi-csrf-token")
            return templates.TemplateResponse(
                "order/forms/order_form.html",
                {
                    "request": request, "event": event_with_prices, "tickets": tickets, "show_modal": True,
                    'insuffisant_place_message': insuffisant_place_message, "buyer_name": buyer_name, 
                    "buyer_phone": buyer_phone, "ticket_type": ticket_type, "quantity": quantity, 
                    'remaining_place': remaining_place, "transaction_id": transaction_id,'csrf_token': csrf_token
                }
            )

        # 5. Création de la commande avec ou sans l'ID de l'utilisateur connecté
        new_order = Order(
            event_id = event_id,
            user_id = session_user_id, # 🌟 MODIFICATION : Sera soit un ID (String) soit None !
            buyer_name = buyer_name,
            buyer_number = clean_phone,  
            ticket_type = ticket_type,
            transaction_id = converted_transaction_id,
            ticket_quantity = quantity,
            total_amount = quantity * ticket.price,
        )
        db.add(new_order)
        await db.flush()  
        order_id = new_order.id  

    # Hors de la transaction, tout est validé proprement
    request.session['code'] = transaction_id
    return RedirectResponse(url=f"/valid_order_response/{event_id}/{order_id}", status_code=303) #redirection vers la page d'attente
@Root.get("/valid_order_response/{event_id}/{order_id}",name="order_response")
async def get_order_response_message(request:Request,event_id:str,order_id:str,db:AsyncSession = Depends(connecting)):
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    order_res = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.tickets)))
    order = order_res.scalars().first()
    tickets = (await db.execute(select(Ticket).where(Ticket.order_id == order_id))).scalars().all()
    if not event or not order:
        return templates.TemplateResponse("order/message/errors/order_error.html", {
            "request": request, 
            "event_id":event_id,
            "detail": "La commande que vous cherchez a disparu !"
        }, status_code=404)
    event_day = get_day(event.date)
    return templates.TemplateResponse("order/message/partials/response.html",{'request':request,'event_day':event_day,'event':event,'order':order,'tickets':tickets})

@Root.get("/get_result/{event_id}/{order_id}",name="")
async def get_order_response_message(request:Request,event_id:str,order_id:str,db:AsyncSession = Depends(connecting)):
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    order_res = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.tickets),selectinload(Order.events)))
    order = order_res.scalars().first()
    if not event or not order:
        raise HTTPException("la commande ou l'evenement n'existe pas")
    event_day = get_day(event.date)
    return templates.TemplateResponse("order/message/partials/card.html",{'request':request,'event_day':event_day,'event':event,'order':order})

@Root.get("/check_order_status/{order_id}")
async def check_order_status(request: Request, order_id: str, db: AsyncSession = Depends(connecting)):
    res = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.events),selectinload(Order.tickets)))
    order = res.scalars().first()
    tickets = (await db.execute(select(Ticket).where(Ticket.order_id == order_id))).scalars().all()
    if not order:
        return HTMLResponse("Commande introuvable", status_code=404)
    
    is_ready = order.paid and order.is_pdf_ready
    
    return templates.TemplateResponse("order/message/partials/card.html", {
        "request": request, 
        "order": order,
        "is_ready": is_ready,
        'tickets':tickets
    })