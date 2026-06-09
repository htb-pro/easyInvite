from fastapi import APIRouter, Depends, Form, HTTPException,Request,Cookie
from fastapi.responses import RedirectResponse,HTMLResponse
from fastapi.templating import Jinja2Templates  
from sqlalchemy import select,asc,desc,func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload,contains_eager
from db_setting import connecting
from models import Order,User,Event,Ticket,Ticket_price
from config import secret,algo
from jose import jwt
from Routers.loging import get_current_user_from_cookie
from app.security.permissions import permission_required
from uuid import uuid4
import urllib.parse,pyotp
from Routers.ticket import get_current_seri,get_current_ticket_number
from arq import create_pool
from config import REDIS_SETTINGS


Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie)])
templates = Jinja2Templates(directory="Templates")  

@Root.get("/participator_phone/{event_id}")#route de recherche d'une commande par le numero de telephone du participant
async def search_participator_phone(request:Request,participator_phone:str,event_id:str,page:int = 1,access_token: str = Cookie(None),db:AsyncSession = Depends(connecting)):
    if not access_token:
        return RedirectResponse("/login") # Rediriger si non connecté
    current_res = jwt.decode(access_token, secret, algorithms=[algo])
    user_id = current_res.get("user")
    
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    user = user_res.scalars().first()
    user_role = user.roles[0].name if user and user.roles else "guest"
    per_page = 50 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0 #le total de commandes
    total_pages = (total_order + per_page - 1) // per_page #le nombre total de page
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0
    total_done_order = (await db.execute(select(func.count()).select_from(Order).where(Order.paid == True))).scalar() or 0 #le nombre de commande traite
    total_undone_order = (await db.execute(select(func.count()).select_from(Order).where(Order.paid == False))).scalar() or 0#le nombre de commande non traite
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0 #le total de commandes        
    res =(select(Order).where(Order.buyer_number.like(f"%{participator_phone}%"),Order.event_id == event_id)\
        .order_by(asc(Order.paid), desc(Order.creation))\
        .offset(offset)\
        .limit(per_page))
    result = await db.execute(res)
    orders = result.scalars().all()
    deleting =request.session.pop("success_deleting",None)

    event = (await db.execute(select(Event).where(Event.id == event_id))).scalars().first()
    if not event :
        raise  HTTPException(status_code=404,detail="event not found")
    return templates.TemplateResponse("order/list/orders.html", {
        'request': request,
        'deleting_message':deleting,
        'done_order':total_done_order,
        'undone_order':total_undone_order,
        'event': event, 
        'event_id': event_id,
        'total_pages': total_pages,
        'total_order': total_order,
        'page': page,
        'orders': orders,
        'total_order': total_order,
        'current_user_role': user_role
    })

@Root.get("/list_orders/{event_id}")
async def get_list_orders(request: Request, event_id: str,  page: int = 1,access_token: str = Cookie(None), db: AsyncSession = Depends(connecting),user=Depends(permission_required("view_order"))):
    # 1. Vérification sécurisée du user
    if not access_token:
        return RedirectResponse("/login") # Rediriger si non connecté
    current_res = jwt.decode(access_token, secret, algorithms=[algo])
    user_id = current_res.get("user")
    
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    user = user_res.scalars().first()
    user_role = user.roles[0].name if user and user.roles else "guest"  
    #------------
    deleting =request.session.pop("success_deleting",None)
     # 2. Pagination
    per_page = 50 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0 #le total de commandes
    total_pages = (total_order + per_page - 1) // per_page #le nombre total de page
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0
    total_done_order = (await db.execute(select(func.count()).select_from(Order).where(Order.paid == True))).scalar() or 0 #le nombre de commande traite
    total_undone_order = (await db.execute(select(func.count()).select_from(Order).where(Order.paid == False))).scalar() or 0#le nombre de commande non traite
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0 #le total de commandes
    orders_query = select(Order).where(Order.event_id == event_id)\
        .order_by(asc(Order.paid), desc(Order.creation))\
        .offset(offset)\
        .limit(per_page)
        
    orders = (await db.execute(orders_query)).scalars().all()
    # 4. Récupération événement
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalars().first()
    
    return templates.TemplateResponse("order/list/orders.html", {
        'request': request,
        'deleting_message':deleting,
        'done_order':total_done_order,
        'undone_order':total_undone_order,
        'event': event, 
        'event_id': event_id,
        'total_pages': total_pages,
        'total_order': total_order,
        'page': page,
        'orders': orders,
        'total_order': total_order,
        'current_user_role': user_role
    })

@Root.get("/get_orders_table/{event_id}")#route qui renvoi le tableau en temps reel avec htmx dans le template
async def get__parial_list_orders(request:Request,event_id:str,page:int = 1 ,access_token: str = Cookie(None),db:AsyncSession = Depends(connecting)):
    if not access_token:
        return RedirectResponse("/login") # Rediriger si non connecté
    deleting =request.session.pop("success_deleting",None)
    current_res = jwt.decode(access_token, secret, algorithms=[algo])
    user_id = current_res.get("user")
    
    user_res = await db.execute(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    user = user_res.scalars().first()
    user_role = user.roles[0].name if user and user.roles else "guest"
    
    per_page = 50 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_order = (await db.execute(select(func.count()).select_from(Order).where(Order.event_id == event_id))).scalar() or 0 #le total de commandes
    total_pages = (total_order + per_page - 1) // per_page #le nombre total de page
    orders_query = select(Order).where(Order.event_id == event_id)\
        .order_by(asc(Order.paid), desc(Order.creation))\
        .offset(offset)\
        .limit(per_page)
        
    orders = (await db.execute(orders_query)).scalars().all()
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalars().first()
    return templates.TemplateResponse("order/message/partials/partial_list_order.html",{'request':request,
    'total_pages': total_pages,
    'page': page,
    'orders': orders,
    'event': event,
    'current_user_role': user_role 
   })

@Root.get("/detail/order/{order_id}")
async def get_detail_orders(request:Request, order_id: str,access_token = Cookie(None),db:AsyncSession = Depends(connecting),user=Depends(permission_required("view_order"))):    
    current_res = jwt.decode(access_token,secret,algorithms = [algo])
    user_id = current_res.get("user")
    if user_id:
        user_res = await db.execute(select(User).where(User.id ==user_id).options(selectinload(User.roles)))
        user = user_res.scalars().first()
        for role in user.roles:
            user_role = role.name
    res = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.events)))
    order = res.scalars().first()
    return templates.TemplateResponse("order/list/detail.html",{'request':request,'order':order,'current_user_role':user_role})

@Root.get("/edit_order_form/{event_id}/{order_id}")
async def get_list_orders(request:Request,event_id:str , order_id: str,db:AsyncSession = Depends(connecting),user = Depends(permission_required("edit_order"))):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order = res.scalars().first()
    ticket_res = await db.execute(select(Ticket_price))
    tickets = ticket_res.scalars().all()
    return templates.TemplateResponse("order/forms/confirm_order.html",{'request':request,'tickets':tickets,'order':order,'event_id':event_id})

# Dans ton fichier où tu valides le paiement

async def trigger_pdf_generation(order_id: str):
    redis = await create_pool(REDIS_SETTINGS)
    await redis.enqueue_job('generate_pdf_task', order_id=order_id)
    print(f"Tâche envoyée pour {order_id}")

@Root.post("/confirm_order/{order_id}")
async def confirm_paiement(
    request: Request,
    order_id: str,
    event_id: str = Form(...),
    buyer_name: str = Form(...), 
    buyer_phone: str = Form(...),   
    quantity: int = Form(...),
    transaction_id: str = Form(...),
    state: bool = Form(...),
    db: AsyncSession = Depends(connecting),
    user = Depends(permission_required("confirm_order"))
):
   
    # 1. Nettoyage strict du numéro pour WhatsApp
    clean_phone = "".join(filter(str.isdigit, buyer_phone))
    if clean_phone.startswith("0"):
        clean_phone = "243" + clean_phone[1:]

    # 2. Récupération de la commande
    res = await db.execute(select(Order).where(Order.id == order_id).options(selectinload(Order.tickets)))
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    # CAS 1 : LE PAIEMENT EST VALIDÉ (state == True)
    if state: 
        if order.paid:
            ticket_res = await db.execute(select(Ticket_price))
            tickets = ticket_res.scalars().all()
            existing_order="Cette commande à été déjà confirmée"
            return templates.TemplateResponse("order/forms/confirm_order.html",{'request':request,'tickets':tickets,'order':order,'event_id':event_id,'existing_order_message':existing_order})
        order.paid = True
        tickets_created = []
        
        try:
            # Sécurité : On vérifie si les tickets n'ont pas déjà été générés
            existing_tickets = await db.execute(select(Ticket).where(Ticket.order_id == order.id))
            tickets = existing_tickets.scalars().all()
            if not tickets:#si le ticket n'existent pas dans la db
                
                # On génère la quantité exacte de tickets demandés
                for i in range(quantity):
                    ticket_get_pass = str(uuid4())[:8]
                    display_name = buyer_name if i == 0 else f"Invité de {buyer_name} ({i+1})"
                    ticket_seri = await get_current_seri(event_id,db)
                    ticket_number = await get_current_ticket_number(event_id,db)
                    totp_value = pyotp.random_base32()
                    print("f============================================{totp_value}")
                    new_ticket = Ticket(
                        order_id=order.id, # Attachement à la commande
                        event_id=event_id,
                        participator_name=display_name,
                        participator_number = buyer_phone,
                        seri = ticket_seri,
                        number = ticket_number,
                        qr_token=str(uuid4()),
                        get_pass=ticket_get_pass,
                        totp_secret=totp_value,
                        is_scanned=False
                    )
                    db.add(new_ticket)
                    await db.flush()#ajoute temporairement le ticket dans la db
                    tickets_created.append(new_ticket)
                await db.commit()
                await trigger_pdf_generation(order.id)
            # Récupération des IDs générés
            for t in tickets_created:
                await db.refresh(t)
                
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Erreur lors de la génération des tickets : {str(e)}")

        # 📄 Message WhatsApp avec la liste des liens vers les TICKETS
        tickets_a_envoyer = tickets_created if tickets_created else order.tickets

        # 📄 Message WhatsApp avec la liste des liens vers CHAQUE TICKET
        message = f"*VOTRE COMMANDE EASYINVITE VALIDÉE*\n\n"
        message += f"Bonjour {buyer_name}, votre paiement a été vérifié. Voici les liens individuels pour vos {quantity} ticket(s) :\n\n"
        
        # 🎯 Enumerate permet d'afficher "Billet 1", "Billet 2", etc.
        for index, ticket in enumerate(tickets_a_envoyer, start=1):
            ticket_url = f"https://easyinvite-1.onrender.com/ticket/view/{event_id}/{ticket.id}"
            message += f"🎟️ *Billet {index}* ({ticket.participator_name}) :\n🔗 {ticket_url}\n\n"
        
        message += "*Note :* Présentez ces billets à l'entrée de l'événement. Le QR code se met à jour automatiquement toutes les 30 secondes pour votre sécurité. Vous pouvez transférer ces liens à vos proches s'ils entrent séparément. 🎉"

        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"
        return RedirectResponse(url=whatsapp_url, status_code=303)

    # CAS 2 : LE PAIEMENT EST REJETÉ (state == False)
    message = (
        f"*PROBLÈME DE VALIDATION DE COMMANDE*\n\n"
        f"Bonjour {buyer_name},\n\n"
        f"Après vérification, nous ne trouvons aucune transaction avec le code *{transaction_id}*.\n\n"
        f"Votre commande est suspendue. Merci de répondre à ce message en joignant une capture d'écran de votre reçu de paiement Mobile Money pour débloquer vos tickets."
    )
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"
    return RedirectResponse(url=whatsapp_url, status_code=303)

@Root.post("/delete_order/{order_id}")
async def delete_order(request: Request, order_id: str, user=Depends(permission_required("delete_order")), db: AsyncSession = Depends(connecting)):
    res = await db.execute(select(Order).where(Order.id == order_id))
    order_to_delete = res.scalars().first()
    
    if not order_to_delete:
        raise HTTPException(status_code=404, detail="Cette commande n'existe pas")
    
    # Récupérer l'ID de l'événement AVANT de supprimer
    event_id = order_to_delete.event_id 
    
    try:
        await db.delete(order_to_delete)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Erreur lors de la suppression")
    
    request.session["success_deleting"] = "🎉 Commande supprimée avec succès !"
    
    # Rediriger vers la liste des commandes de l'événement
    return RedirectResponse(f"/list_orders/{event_id}", status_code=303)