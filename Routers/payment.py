from fastapi import APIRouter, Depends, Form, HTTPException,Request,status
from fastapi.responses import RedirectResponse,HTMLResponse
from fastapi.templating import Jinja2Templates  
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from db_setting import connecting
from models import Event,Order,Ticket_price,Ticket,ExternalUser
from Routers.invite import get_day
from fastapi_csrf_protect import CsrfProtect
from jose import jwt 
from config import secret,algo,csrf_key,verify_csrf
import secrets
from itsdangerous import URLSafeTimedSerializer, BadSignature


Root = APIRouter()
templates = Jinja2Templates(directory="Templates")  



@Root.get("/payments/{event_id}")
async def get_paiement_view(request:Request, event_id: str,db:AsyncSession = Depends(connecting)):
    csrf_token = secrets.token_urlsafe(32)
    event = (await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices)))).scalars().first()
    invalid_number = request.session.pop('invalid_number',None)
    response = templates.TemplateResponse(
        "order/forms/order_form.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "event_id": event_id,
            'event':event,
            'invalid_phone_number':invalid_number
        }
    )

    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=True,  # le frontend doit pouvoir le lire
        secure=True,
        samesite="strict",
        
    )

    return response

@Root.get("/success",name="success")
async def get_success_message(request:Request):
    transaction_id = request.session.pop("code",None)
    return templates.TemplateResponse("order/message/success.html",{'request':request,'transaction_id':transaction_id})

# 1. Tu prépares le décodeur avec ta clé secrète
serializer = URLSafeTimedSerializer(csrf_key)
@Root.post("/make_order/{event_id}")
async def get_paiement_data(request:Request, event_id: str, buyer_name: str = Form(...), buyer_phone: str = Form(...),  ticket_type: str = Form(...), quantity: int = Form(...),transaction_id = Form(...),db: AsyncSession = Depends(connecting),_:None = Depends(verify_csrf)):
    converted_transaction_id = transaction_id.lower() #Conversion de id de transaction
    event_res = await db.execute(select(Event).where(Event.id == event_id))
    event = event_res.scalars().first()
    ticket_res = await db.execute(select(Ticket_price).where(Ticket_price.ticket_type == ticket_type))
    ticket = ticket_res.scalars().first()#pour le calcule du montant a transfere Qte * prix de billet
    order_res = await db.execute(select(Order).where(Order.transaction_id == converted_transaction_id,Order.event_id == event_id))
    order = order_res.scalars().first()
    # # L'extension vérifie automatiquement le token si tu ajoutes ce décorateur    
    # # 1. Récupération des jetons
    # form = await request.form()
    # received_token = form.get("csrf_token")
    # signed_token = request.cookies.get("fastapi-csrf-token")   
    # if not signed_token or not received_token:
    #     raise HTTPException(status_code=403, detail="Données manquantes")
    # try:
    #     # A. On tente d'ouvrir
    #     raw_decoded = serializer.loads(signed_token,max_age=None)
    #     # Nettoyage des guillemets éventuels
    #     expected_token = str(raw_decoded).strip('"')
        
    #     # B. Comparaison
    #     resultat_comparaison = hmac.compare_digest(received_token, expected_token)
        
    #     # LOGS VITAUX POUR COMPRENDRE
    #     print(f"DEBUG: Token attendu : {expected_token}")
    #     print(f"DEBUG: Token reçu    : {received_token}")
    #     print(f"DEBUG: Résultat comparaison : {resultat_comparaison}")
        
    #     if not resultat_comparaison:
    #         raise HTTPException(status_code=403, detail="Jeton CSRF invalide")
            
    # except Exception as e:
    #     # C'est ici que tu verras l'erreur réelle dans le terminal
    #     print(f"DEBUG: ERREUR CRITIQUE DANS LA VALIDATION : {type(e).__name__} - {str(e)}")
    #     raise HTTPException(status_code=403, detail="Erreur de validation")
    # # except Exception as e:
    # #     raise HTTPException(status_code=403, detail="Erreur de validation")
    # #     print(f"DEBUG: Erreur détaillée dans try/except : {type(e).__name__} - {e}")
    # #     #return templates.TemplateResponse("Authentification/admin/admin_required_message.html",{'request':request})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if order: 
        csrf_token = secrets.token_urlsafe(32)
        res = await db.execute(select(Ticket_price)) #a renvoyer pour la liste d'options sur le form de commande
        tickets = res.scalars().all()
        event = (await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices)))).scalars().first()
        exist_message = "Ce code de transaction a déjà été utilisé, si vous pensez qu'il s'agit d'une erreur, veillez verifier le code saisi ou contacter notre service support"
        return templates.TemplateResponse("order/forms/order_form.html",{'request':request, "csrf_token": csrf_token,'event':event,'tickets':tickets,'exist_message':exist_message,'buyer_name':buyer_name,'buyer_phone':buyer_phone,'ticket_type':ticket_type,'quantity':quantity,'transaction_id':transaction_id})
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
    try:
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
        await db.commit()
        await db.refresh(new_order)
    except Exception as e:
         await db.rollback()
         print(f"---------------------------------{e}")
         raise HTTPException(status_code=500, detail="Error occurred while saving the order")
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