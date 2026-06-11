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
async def get_paiement_data(request:Request, event_id: str, buyer_name: str = Form(...), buyer_phone: str = Form(...),  ticket_type: str = Form(...), quantity: int = Form(...),transaction_id = Form(...),_=Depends(verify_csrf),db: AsyncSession = Depends(connecting)):
    converted_transaction_id = transaction_id.lower() #Conversion de id de transaction
    new_order =None
    tickets_sold =None
    async with db.begin():
        # 2. On récupère l'événement ET ON LE VERROUILLE (.with_for_update())
        # Ça empêche deux requêtes simultanées de lire le même nombre de places
        event_result = await db.execute(
            select(Event).where(Event.id == event_id).with_for_update()
        )
        event = event_result.scalar_one_or_none()    
        ticket_res = await db.execute(select(Ticket_price).where(Ticket_price.ticket_type == ticket_type))
        ticket = ticket_res.scalars().first()#pour le calcule du montant a transfere Qte * prix de billet
        order_res = await db.execute(select(Order).where(Order.transaction_id == converted_transaction_id,Order.event_id == event_id))
        order = order_res.scalars().first()
        
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        if order: 
            csrf_token = secrets.token_urlsafe(32)
            res = await db.execute(select(Ticket_price)) #a renvoyer pour la liste d'options sur le form de commande
            tickets = res.scalars().all()
            # Re-chargement de l'event avec ses relations pour le formulaire
            event_with_prices = (await db.execute(
                select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices))
            )).scalars().first()
              # 2. On compte combien de billets ont déjà été vendus
            tickets_sold = await db.scalar(
                select(func.count(Ticket.id)).where(Ticket.event_id == event_id)
            ) or 0
            
            if tickets_sold:
                # 3. ON CALCULE LES PLACES RESTANTES 📊
                remaining_place = event.total_capacity - tickets_sold
                
                # Si jamais le calcul donne un chiffre négatif par accident, on le remet à 0
                
                if remaining_place < 0:
                    remaining_place = 0
            exist_message = "Ce code de transaction a déjà été utilisé, si vous pensez qu'il s'agit d'une erreur, veillez verifier le code saisi ou contacter notre service support"
            return templates.TemplateResponse("order/forms/order_form.html",{'request':request, "csrf_token": csrf_token,'event':event_with_prices,'tickets':tickets,'exist_message':exist_message,'buyer_name':buyer_name,'buyer_phone':buyer_phone,'ticket_type':ticket_type,'quantity':quantity,'transaction_id':transaction_id,'remaining_place':remaining_place})
        clean_phone = "".join(filter(str.isdigit, buyer_phone))
        if not clean_phone:
            request.session['invalid_number'] = "Format du numéro de téléphone invalide"
            return RedirectResponse(
            f"/payments/{event_id}",
                status_code=303
            )
            
        if clean_phone.startswith("0"):
            clean_phone = "243" + clean_phone[1:]
        new_order = None
        #creation du compte du participant directement 
            #la verification de place 
        tickets_sold = await db.scalar(
            select(func.count(Ticket.id)).where(Ticket.event_id == event_id)
        ) or 0
        # 4. LE CONTRÔLE CRITIQUE : Est-ce qu'on a atteint la limite (ex: 100) ?
        if tickets_sold:
            if tickets_sold + quantity > event.total_capacity: 
                insuffisant_place_message=" Désolé, cet événement est complet ! Plus aucune place n'est disponible." #si le nombre de billet demander est plus ce que les place restante
                event_with_prices = (await db.execute(
                    select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices))
                )).scalars().first()
                res_tickets = await db.execute(select(Ticket_price))
                tickets = res_tickets.scalars().all()
                tickets_sold = await db.scalar(
                select(func.count(Ticket.id)).where(Ticket.event_id == event_id)) or 0
                # 3. ON CALCULE LES PLACES RESTANTES 📊
                remaining_place = event.total_capacity - tickets_sold
                # Si jamais le calcul donne un chiffre négatif par accident, on le remet à 0
                if remaining_place < 0:
                    remaining_place = 0
                return templates.TemplateResponse(
                    "order/forms/order_form.html",
                    {
                        "request": request,
                        "event": event_with_prices,
                        "tickets": tickets,
                        "show_modal": True,  # Un petit drapeau pour dire au JS d'ouvrir la modal
                        'insuffisant_place_message':insuffisant_place_message,
                        # On ré-injecte ce que l'utilisateur avait tapé :
                        "buyer_name": buyer_name,
                        "buyer_phone": buyer_phone,
                        "ticket_type": ticket_type,
                        "quantity": quantity,
                        'remaining_place':remaining_place,
                        "transaction_id": transaction_id
                    }
                )

            # 3. Récupération ou création de l'utilisateur en une seule étape logique
        res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == clean_phone))
        user = res.scalars().first()
        if not user:
            user = ExternalUser(name=buyer_name,phone_number=clean_phone)
            db.add(user)
            await db.flush()
        ticket_price = ticket.price
        new_order = Order(
            event_id = event_id,
            buyer_name = buyer_name,
            buyer_number = buyer_phone,
            ticket_type = ticket_type,
            transaction_id = converted_transaction_id,
            ticket_quantity  = quantity,
            user_id = user.id,
            total_amount =  quantity * ticket_price, #total a payer pour le ticket
        )
        db.add(new_order)
    request.session['code'] = transaction_id
    order_id = new_order.id
    return RedirectResponse(url=f"/valid_order_response/{event_id}/{order_id}", status_code=303)

#reponse a envoyer a l'utilisateur une fois commande valide
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