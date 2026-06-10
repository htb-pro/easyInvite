from datetime import datetime
from fastapi import APIRouter, Request, Form,Depends,Cookie,HTTPException,status
from fastapi.responses import HTMLResponse, RedirectResponse,Response ,StreamingResponse,JSONResponse
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates  
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc
from sqlalchemy.orm import selectinload
from db_setting import connecting
from config import secret, algo,REDIS_SETTINGS
import jwt,random,io
from models import User, Order, Event,ExternalUser,OTP
from app.security.permissions import permission_required
from datetime import datetime, timedelta,timezone
from utils.sms_setting.sms_utils import send_otp_sms
from utils.redis_config import redis_conn
from uuid import UUID
from arq import create_pool

templates = Jinja2Templates(directory="Templates")
Root = APIRouter()
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static

@Root.get("/get/event_name")#route de recherche d'une commande par le numero de telephone du participant
async def search_event(request:Request,event_name:str,page:int = 1,db:AsyncSession = Depends(connecting)):
    search_name = event_name.upper()
    per_page = 50 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_events = (await db.execute(select(func.count()).select_from(Event).where(Event.type == "other"))).scalar() or 0 #le total d'événements
    total_pages = (total_events + per_page - 1) // per_page #le nombre total de page
    res =(select(Event).where(Event.name.ilike(f"%{event_name}%"),Event.type == "other").options(selectinload(Event.ticket_prices))\
        .order_by(asc(Event.created_date), desc(Event.created_date))\
        .offset(offset)\
        .limit(per_page)) # rechercher la donnee renseigner dans la barre de recherche, ilike permet d'ignorer le magiscule ou miniscule
    result = await db.execute(res)
    events = result.scalars().all()
    copyright = datetime.now().year
    return templates.TemplateResponse("external_user/list/events.html", {
        'request': request,
        'total_pages': total_pages,
        'page': page,
        'events': events,
        'copyright': copyright,
    })

@Root.get("/event/list", response_class=HTMLResponse)#list des evenement
async def get_list_of_events(request: Request,  page: int = 1, db: AsyncSession = Depends(connecting)):
    #------------
    user_name = None
    current_user_id = request.cookies.get("session_user_id")
    if current_user_id:
        user = (await db.execute(select(ExternalUser).where(ExternalUser.id == current_user_id))).scalars().first()
        if user:
            user_name = user.name
     # 2. Pagination
    per_page = 10 #notre d'items par page
    offset = (page - 1) * per_page #decalage
    total_event = (await db.execute(select(func.count()).select_from(Event).where(Event.type == "other"))).scalar() or 0 #le total de commandes
    total_pages = (total_event + per_page - 1) // per_page #le nombre total de page
    orders_query = select(Event).where(Event.type == "other").options(selectinload(Event.ticket_prices))\
        .order_by(desc(Event.created_date))\
        .offset(offset)\
        .limit(per_page)
        
    events = (await db.execute(orders_query)).scalars().all()
    copyright = datetime.now().year
    # 4. Récupération événements et rendu du template    
    return templates.TemplateResponse("external_user/list/events.html", {
        'request': request,
        'total_pages': total_pages,
        'total_event': total_event,
        'page': page,
        'events': events,
        'copyright': copyright,
        'user': user_name
    })

@Root.get("/event/details/{event_id}")#la root pour voir les detail d'un event
async def eventDetail(request:Request,event_id : str,access_token = Cookie(None),db:AsyncSession = Depends(connecting)):
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalars().first()
    if not event:
        return RedirectResponse("/event/list")
    event_img = event.photo_url if event.photo_url else None
    return templates.TemplateResponse("external_user/list/detail.html",{'request':request,"event":event,'event_img':event_img})

#----------------------------OTP
@Root.get("/my_account")
async def mon_compte_participant(
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'authentification via le cookie
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        # Si le participant n'est pas connecté, redirection flash vers la page de login
        request.session['invalid_number'] = "Veuillez vous connecter pour accéder à vos billets."
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        # 2. Récupération de l'utilisateur pour afficher ses infos (optionnel mais pro)
        user_res = await db.execute(select(ExternalUser).where(ExternalUser.id == user_id))
        current_user = user_res.scalars().first()
        
        if not current_user:
            # Sécurité si le cookie contient un ID qui n'existe plus en BDD
            response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie("session_user_id")
            return response

        # 3. Requête ultra-optimisée avec jointures chargées en mémoire (Eager Loading)
        # On ne prend que les commandes PAYÉES (Order.paid == True)
        result = await db.execute(
            select(Order)
            .where(Order.user_id == user_id, Order.paid == True) # on recupere ses commande deja payer
            .options(
                selectinload(Order.events),   # Jointure pour récupérer le titre/date de l'événement
                selectinload(Order.tickets)  # Jointure pour récupérer la liste des tickets associés
            )
            .order_by(Order.creation.desc()) # Les billets les plus récents en premier
        )
        orders = result.scalars().all()
        
    except Exception as e:
        print(f"Erreur lors du chargement de l'espace compte pour l'user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger vos billets pour le moment."
        )

    # 4. Envoi des données triées au template HTML
    return templates.TemplateResponse(
        "external_user/my_account/my_account.html", 
        {
            "request": request, 
            "orders": orders,
            "user_name": current_user.name # Permet d'afficher "0991..." dans la navbar
        }
    )

@Root.get("/auth/login")
async def login_page(request: Request, db: AsyncSession = Depends(connecting)):
    # 1. Récupération du message d'erreur flash (ex: numéro invalide)
    invalid_phone_number = request.session.pop('invalid_number', None)
    
    # 2. Vérification si l'utilisateur possède déjà un cookie de session
    current_user_id = request.cookies.get("session_user_id")
    print(f"--- DEBUG COOKIE LOGIN PAGE : {current_user_id}")
    
    if current_user_id:
        try:
            # On vérifie si cet ID existe vraiment en BDD
            res = await db.execute(select(ExternalUser).where(ExternalUser.id == current_user_id))
            user = res.scalars().first()
            
            if user:
                # 🔥 L'utilisateur est DÉJÀ connecté ! On le redirige vers son compte
                # Au lieu de le forcer à se reconnecter
                return RedirectResponse(url="/my_account", status_code=status.HTTP_303_SEE_OTHER)
                
        except Exception as e:
            print(f"Erreur vérification user existant au login: {str(e)}")
            # En cas de problème, on nettoie le cookie suspect
            response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie("session_user_id")
            return response

    # 3. COMPORTEMENT NORMAL : Si PAS de cookie (ou cookie invalide)
    # On affiche simplement le formulaire HTML de connexion
    return templates.TemplateResponse(
        "external_user/forms/send_number_form.html", # 🎯 Utilise ton template de formulaire de login ici !
        {
            "request": request, 
            "invalid_phone_number": invalid_phone_number
        }
    )

@Root.post("/auth/request-otp")
async def request_otp(
    phone: str = Form(...), 
    name: str = Form(...), 
    db: AsyncSession = Depends(connecting)
):
    # 1. Validation et Nettoyage strict du numéro
    clean_phone = "".join(filter(str.isdigit, phone))
    if not clean_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Format du numéro de téléphone invalide."
        )
        
    if clean_phone.startswith("0"):
        clean_phone = "243" + clean_phone[1:]
        
    # 2. Génération de l'OTP
    generated_otp = str(random.randint(1000, 9999))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    expiration_time = now + timedelta(minutes=5)
    
    try:
        # 3. Récupération ou création de l'utilisateur
        res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == clean_phone))
        user = res.scalars().first()
        
        if not user:
            user = ExternalUser(phone_number=clean_phone,name=name)
            db.add(user)
            await db.flush() # Assure la génération de user.id
            
        # 4. Upsert de l'OTP
        otp_res = await db.execute(select(OTP).where(OTP.ext_user_id == user.id))
        current_otp = otp_res.scalars().first()
        
        if current_otp:
            current_otp.code = generated_otp
            current_otp.expires_at = expiration_time
        else:
            current_otp = OTP(
                ext_user_id=user.id,
                code=generated_otp,
                expires_at=expiration_time
            )
            db.add(current_otp)
            
        # 🔥 ENVOI DU SMS VIA AFRICA'S TALKING (Avec await et sans accolades)
        #sms_sent = await send_otp_sms(clean_phone, generated_otp)
        print(f"==============={clean_phone}, {generated_otp}")
        
        # if not sms_sent:
        #     # Optionnel : Tu peux choisir de bloquer ou de logger si le SMS échoue
        #     print(f"⚠️ Alerte : Le SMS n'a pas pu être envoyé à {clean_phone}")
            
        await db.commit()
        
    except Exception as e:
        await db.rollback()
        print(f"Erreur lors de la demande OTP pour {clean_phone}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Une erreur interne est survenue. Veuillez réessayer."
        )
    
    # 5. Redirection Sécurisée vers la page de vérification
    response = RedirectResponse(
        url=f"/auth/verify-otp-page?phone={clean_phone}", 
        status_code=status.HTTP_303_SEE_OTHER
    )
    return response

@Root.get("/auth/verify-otp-page")
async def verify_otp_page(request: Request, phone: str):
    """
    Cette route intercepte le GET du navigateur après la génération de l'OTP.
    L'URL ressemblera à : http://127.0.0.1:8000/auth/verify-otp-page?phone=243991635198
    """
    # On renvoie le fichier HTML en lui passant le numéro de téléphone.
    # Ainsi, Jinja2 pourra l'afficher à l'écran et l'injecter dans le champ caché <input type="hidden">
    incorect_otp = request.session.pop('incorrect_otp',None)
    return templates.TemplateResponse(
        "external_user/forms/verify_otp.html", 
        {
            "request": request, 
            "phone": phone,
            "incorrect_otp_message":incorect_otp
        }
    )

@Root.post("/auth/verify-otp")
async def verify_otp(
    request: Request,
    phone: str = Form(...), 
    otp_entered: str = Form(...), 
    db: AsyncSession = Depends(connecting)
):
    # 1. Récupérer l'utilisateur correspondant au numéro
    res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone))
    user = res.scalars().first()
    
    if not user:
        request.session['invalid_number'] = "Veuillez entrer votre numéro pour commencer."
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    # Récupération de l'OTP
    otp_res = await db.execute(select(OTP).where(OTP.ext_user_id == user.id))
    current_otp = otp_res.scalars().first()
    
    # 🎯 SÉCURITÉ ULTRA : On vérifie si l'OTP existe ET s'il n'a pas déjà été consommé (None)
    if not current_otp or current_otp.code is None:
        request.session['incorrect_otp'] = "Aucun code actif trouvé ou code déjà utilisé. Veuillez en demander un nouveau."
        return RedirectResponse(f"/auth/verify-otp-page?phone={phone}", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Sécurité : Vérifier si l'OTP correspond
    if current_otp.code != otp_entered:
        request.session['incorrect_otp'] = "Le code entré est incorrect."
        return RedirectResponse(f"/auth/verify-otp-page?phone={phone}", status_code=status.HTTP_303_SEE_OTHER)
        
    # Vérifier l'expiration (Comparaison naïve pour PostgreSQL)
    if datetime.now(timezone.utc).replace(tzinfo=None) > current_otp.expires_at:
        request.session['invalid_otp'] = "Code OTP expiré. Veuillez en demander un nouveau."
        return RedirectResponse(f"/auth/verify-otp-page?phone={phone}", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        # 3. L'OTP est valide ! On le consomme en le vidant
        current_otp.code = None  
        await db.commit()
        
    except Exception as e:
        print("----------------{e}------------------")
        raise HTTPException(
            status_code=500,
            detail="Une erreur interne est survenue. Veuillez réessayer."
        )
    
    # 4. AUTHENTIFICATION & REDIRECTION 🎉
    response = RedirectResponse(url="/my_account", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_user_id", value=user.id, httponly=True)
    
    return response

@Root.get("/auth/logout")
async def logout(request: Request):

    # 1. Préparation de la redirection vers la page de login
    response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    
    # 2. Suppression du cookie d'authentification
    response.delete_cookie(key="session_user_id")
    
    # 3. Optionnel : Nettoyage de la session Starlette si tu veux vider les messages flash en même temps
    request.session.clear()
    
    return response

#-----------------------------------------------external_user ticket
@Root.get("/download/ticket/{ticket_id}/{order_id}")#telechargement d'un billet 
async def download_single_ticket(  
    ticket_id: UUID, 
    order_id: UUID, 
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    result = await db.execute(select(Order).where(Order.id == str(order_id)))
    order = result.scalar_one_or_none()
    if not order or not order.paid:
        raise HTTPException(status_code=403, detail="Commande invalide ou non payée.")

    # 🎯 2. CORRECTION CLÉ REDIS : Utilise la même clé que le Worker ('ticket_pdf_cache:')
    pdf_bytes = await redis_conn.get(f"ticket_pdf_cache:{ticket_id}")
    
    if not pdf_bytes:
        # SÉCURITÉ ABSOLUE : Initialisation du pool ARQ au besoin
        if not hasattr(request.app.state, "arq_pool") or request.app.state.arq_pool is None:
            print("⚠️ [ROUTE] arq_pool était None, initialisation manuelle en cours...")
            request.app.state.arq_pool = await create_pool(REDIS_SETTINGS)
            
        pool = request.app.state.arq_pool
        
        # 🎯 3. CORRECTION DU NOM DE LA TÂCHE ARQ : appeler 'generate_ticket_pdf_task'
        # Et on lui passe bien les arguments attendus par ton worker unitaire !
        await pool.enqueue_job('generate_ticket_pdf_task', str(ticket_id), str(order_id))
        print(f"🚀 [ROUTE] Tâche envoyée avec succès pour le ticket unique {ticket_id}")
        
        return templates.TemplateResponse(
            "order/message/partials/waiting_page.html", 
            {"request": request, "ticket_id": ticket_id, "order_id": order_id},
            status_code=202 # On peut quand même garder le statut 202
        )
    
    # 🎯 4. CORRECTION FILENAME : Le fichier ne contient qu'UN seul billet, on le nomme d'après le ticket_id
    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Billet_{ticket_id}.pdf"}
    )

#la route de telechargement de tous les billets d'une commmande
@Root.get("/download/order/{order_id}")
async def download_all_order_tickets(
    order_id: UUID, 
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    # ... tes vérifications de commande habituelles (order.paid, etc.) ...

    # 1. Vérification dans le cache Redis
    pdf_bytes = await redis_conn.get(f"pdf_cache:{order_id}")
    
    if not pdf_bytes:
        # 🎯 SÉCURITÉ ABSOLUE : Si le state est None, on crée le pool à la volée !
        if not hasattr(request.app.state, "arq_pool") or request.app.state.arq_pool is None:
            print("⚠️ [ROUTE] arq_pool était None, initialisation manuelle en cours...")
            request.app.state.arq_pool = await create_pool(REDIS_SETTINGS)
            
        # Maintenant, on est sûr à 100% qu'il n'est plus None !
        pool = request.app.state.arq_pool
        
        # 2. Envoi de la tâche au Worker ARQ
        await pool.enqueue_job('generate_pdf_task', str(order_id))
        print(f"🚀 [ROUTE] Tâche envoyée avec succès pour la commande {order_id}")
        
        # 3. Retour de la salle d'attente (VWR)
        return templates.TemplateResponse(
            "order/message/partials/waiting_page_order.html", 
            {"request": request, "order_id": order_id},
            status_code=202 # On peut quand même garder le statut 202
        )
    
    # 4. SCÉNARIO B : Le PDF est prêt ! On le distribue au format binaire
    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Billets_Commande_{order_id}.pdf"}
    )
