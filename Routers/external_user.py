from datetime import datetime, time
from fastapi import APIRouter, Request, Form,Depends,Cookie,HTTPException,status,responses
from fastapi.responses import HTMLResponse, RedirectResponse,Response ,StreamingResponse,JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates  
from requests import request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc
from sqlalchemy.orm import selectinload
from db_setting import connecting
from config import secret, algo,REDIS_SETTINGS,set_secure_cookie,verify_csrf
import jwt,random,io,secrets,urllib
from models import Ticket_price, User, Order, Event,ExternalUser,OTP,Ticket
from app.security.permissions import permission_required
from datetime import datetime, timedelta,timezone
from utils.sms_setting.sms_utils import send_otp_sms
from utils.redis_config import redis_conn
from uuid import UUID
from arq import create_pool
from urllib.parse import quote
from Routers.loging import hash_password,verify_password


templates = Jinja2Templates(directory="Templates")
Root = APIRouter()
Root.mount("/static",StaticFiles(directory="static"),name="static")#ou sont stocker les fichier static

#--------------------------------------------------methodes
def format_to_drc_phone(raw_phone: str) -> str: #methode pour formater le numero de telephone entrer par le user en format congolais
    # 1. On ne garde que les chiffres
    digits = "".join(filter(str.isdigit, raw_phone))
    
    # 2. Si ça commence par 0, on enlève le 0 et on met 243 (ex: 081... -> 24381...)
    if digits.startswith("0") and len(digits) == 10:
        return "243" + digits[1:]
        
    # 3. Si l'utilisateur a tapé directement 81... sans le 0 ni le 243 (9 chiffres)
    if len(digits) == 9 and not digits.startswith("243"):
        return "243" + digits
        
    # 4. Si c'est déjà au format 243... (12 chiffres)
    if digits.startswith("243") and len(digits) == 12:
        return digits
        
    # Renvoie le résultat nettoyé, ou le brut si le format est inconnu
    return digits

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
    return templates.TemplateResponse("e-ticket/main/main_page.html", {
        'request': request,
        'total_pages': total_pages,
        'page': page,
        'events': events,
        'copyright': copyright,
    })

@Root.get("/e-ticket", response_class=HTMLResponse)#list des evenement
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
    query = select(Event).where(Event.type == "other",Event.is_featured == True).options(selectinload(Event.ticket_prices))\
        .order_by(desc(Event.created_date))\
        .offset(offset)\
        .limit(per_page)
    featured_events = (await db.execute(query)).scalars().all()
    from models import Ticket
    
    #print(f"--------------------{remaining_place}----------------------------")
    copyright = datetime.now().year
    # 4. Récupération événements et rendu du template    
    return templates.TemplateResponse("e-ticket/main/index.html", {
        'request': request,
        'total_pages': total_pages,
        'total_event': total_event,
        'page': page,
        'events': events,
        'featured_events': featured_events,
        'copyright': copyright,
        'user': user_name
    })

@Root.get("/event/list", response_class=HTMLResponse) # liste des événements
async def get_list_of_events(
    request: Request,
    search: str = None, 
    city: str = None, 
    category: str = None,
    filter_date: str = None,
    page: int = 1,
    db: AsyncSession = Depends(connecting)
):
    per_page = 10
    offset = (page - 1) * per_page
    now = datetime.now()
    
    # Sécurité de base : uniquement les événements valides et non supprimés
    base_query = select(Event).where(Event.type == "other", Event.is_deleted == False)
    
    # 1. Gestion du filtre de date
    if filter_date == "today":
        # Début et fin de la journée d'aujourd'hui
        start_of_today = datetime.combine(now.date(), time.min)
        end_of_today = datetime.combine(now.date(), time.max)
        base_query = base_query.where(Event.date >= start_of_today, Event.date <= end_of_today)
    elif filter_date == "upcoming":
        # Événements futurs à partir de maintenant
        base_query = base_query.where(Event.date >= now)
    
    # 2. On ajoute les filtres de recherche textuelle et géographique
    if search:
        base_query = base_query.where(Event.name.ilike(f"%{search}%"))
    if city:
        base_query = base_query.where(Event.location == city)

    # 3. Calcul du total d'événements correspondants pour la pagination
    count_query = select(func.count()).select_from(base_query.subquery())
    total_event = (await db.execute(count_query)).scalar() or 0
    total_pages = (total_event + per_page - 1) // per_page

    # 4. Tri, chargement des prix de billets associés et découpage de la page
    final_query = (
        base_query
        .options(selectinload(Event.ticket_prices))
        .order_by(Event.date.asc())
        .offset(offset)
        .limit(per_page)
    )
    
    res = await db.execute(final_query)
    events = res.scalars().all()
    
    # 5. Envoi des données filtrées au HTML
    return templates.TemplateResponse("e-ticket/event/list.html", {
        'request': request,
        'events': events,
        'page': page, # ou 'page': page selon ton HTML
        'total_pages': total_pages,
        'search': search,
        'city': city,
        'filter_date': filter_date
    })

@Root.get("/policy", response_class=HTMLResponse)#list des evenement
async def get_policy_page(request: Request):
    # 4. Récupération événements et rendu du template    
    return templates.TemplateResponse("e-ticket/policy/policy.html", {
        'request': request,
    })

@Root.get("/privacy", response_class=HTMLResponse)#list des evenement
async def get_privacy_page(request: Request):
    # 4. Récupération événements et rendu du template    
    return templates.TemplateResponse("e-ticket/privacy/privacy.html", {
        'request': request,
    })

@Root.get("/pricing", response_class=HTMLResponse)#list des evenement
async def get_pricing_page(request: Request):
    # 4. Récupération événements et rendu du template    
    return templates.TemplateResponse("e-ticket/pricing/pricing.html", {
        'request': request,
    })

@Root.get("/event/details/{event_id}")#la root pour voir les detail d'un event
async def eventDetail(request:Request,event_id : str,access_token = Cookie(None),db:AsyncSession = Depends(connecting)):
    csrf_token = secrets.token_urlsafe(32)
    event = (await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.ticket_prices)))).scalars().first()
    if not event:
        return RedirectResponse("/event/list")
    event_img = event.photo_url if event.photo_url else None
    return templates.TemplateResponse("e-ticket/event/detail.html",{'request':request,"event":event,'event_img':event_img})

@Root.get("/support_team_contact")# le lien qui ouvrire whatsapp pour laisser le user donner sa demande ou probleme
async def send_whatsapp_redirect(request:Request):    
    support_contact = "+243897401210"
    suport_name = "E-event"
    # 2. Préparer les données
    message = f"Demande d'aide\n\nBonjour  l'équipe {suport_name}, ! \n\n👋J'utilise l'application et j'ai besoin d'aide\n\n "
    # 3. Nettoyer le numéro (ne garder que les chiffres)
    # On suppose que le numéro est stocké avec l'indicatif pays (ex: 243...)
    clean_phone = "".join(filter(str.isdigit, support_contact))
    # 4. Encoder le message pour l'URL
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"
    
    # 5. Rediriger l'utilisateur directement vers WhatsApp
    return RedirectResponse(url=whatsapp_url)
#---------------------------------organisateur
@Root.get("/organizer/dashboard")
async def organisar_dashboard(request: Request):
    return templates.TemplateResponse("e-ticket/organizer/dashboard.html", {
        'request': request,
    })

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
        # 3. Requête ultra-optimisée via l'ID de l'utilisateur (Immuable !)
        result = await db.execute(
            select(Order)
            .where(Order.user_id == current_user.id, Order.paid == True) # 👈 Filtrage par ID sécurisé
            .options(
                selectinload(Order.events),   
                selectinload(Order.tickets)  
            )
            .order_by(Order.creation.desc())
        )
        orders = result.scalars().all()

        # Calcul du total USD (basé sur l'ID utilisateur)
        total_amount_usd_res = await db.execute(
            select(func.sum(Order.total_amount))
            .where(Order.user_id == current_user.id, Order.paid == True)
        )
        total_anount_usd = total_amount_usd_res.scalar() or 0.0

        # Calcul du total CDF (basé sur l'ID utilisateur)
        total_anount_cdf = await db.scalar(
            select(func.sum(Order.total_amount))
            .where(Order.user_id == current_user.id, Order.paid == True)
        ) or 0.0

        # Nombre de tickets achetés (Si ta table Ticket possède un champ user_id, utilise-le !)
        # Nombre de tickets payés (en passant par la jointure avec Order)
        baught_tickets = await db.scalar(
            select(func.count())
            .select_from(Ticket)
            .join(Order, Ticket.order_id == Order.id) # 👈 On lie le ticket à sa commande
            .where(Order.user_id == current_user.id, Order.paid == True) # 👈 On filtre sur l'ID de l'utilisateur et les commandes payées
        ) or 0
        query = (
        select(
                func.sum(Order.ticket_quantity * Ticket_price.price).label("total_usd")
            )
            .join(Event, Order.event_id == Event.id)
            .join(Ticket_price, Ticket_price.event_id == Event.id)
            .where(
                Order.paid == True,
                Order.user_id == current_user.id,
                Event.is_deleted == False,
                Ticket_price.device == "USD"  # 👈 LE FILTRE EST ICI !
            )
        )
        res = await db.execute(query)
        # Comme on ne cherche qu'une seule valeur, on utilise .scalar()
        total_usd = res.scalar() or 0.0
        if total_anount_usd is None:
            total_anount_usd = 0.0
        if total_anount_cdf is None:
            total_anount_cdf = 0.0
        #print(f"=============================={total_usd}")
    except Exception as e:
        print(f"Erreur lors du chargement de l'espace compte pour l'user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger vos billets pour le moment."
        )
        # Dans ton fichier principal (ex: main.py ou partout où tu définis tes templates)
    def get_initials(name: str) -> str:
        if not name:
            return ""
        # On découpe le nom par les espaces, on prend la 1ère lettre de chaque mot et on met en majuscule
        words = name.split()
        initials = [word[0].upper() for word in words if word]
        return "".join(initials[:2]) # On limite à 2 initiales maximum (ex: H.T.)

    # On enregistre le filtre dans Jinja2
    templates.env.filters["initials"] = get_initials
    # 4. Envoi des données triées au template HTML
    return templates.TemplateResponse(
        "external_user/my_account/user_account.html", 
        {
            "request": request, 
            "orders": orders,
            'total_anount_usd':total_anount_usd,
            'total_anount_cdf':total_anount_cdf,
            "current_user":current_user,
            "baught_tickets":baught_tickets,
            "initial_name_current_user": get_initials(current_user.name) if current_user else "",#prenndre les initiales du nom de l'utilisateur pour les afficher dans la navbar
            "user_name": current_user.name if current_user else "" #le nom complet de l'utilisateur pour l'afficher dans la page de profil
        }
    )
@Root.get("/my_ticket")
async def user_tickets(
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
        "external_user/my_account/user_tickets.html", 
        {
            "request": request, 
            "orders": orders,
            #"user_name": current_user.name # Permet d'afficher "0991..." dans la navbar
        }
    )
@Root.get("/user/list_events")
async def user_list_events_json(
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'authentification (Sécurité pour bloquer les robots anonymes)
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
            select(Order) # on recupere ses commande deja payer
            .options(
                selectinload(Order.events),   # Jointure pour récupérer le titre/date de l'événement
                selectinload(Order.tickets)  # Jointure pour récupérer la liste des tickets associés
            )
            .order_by(Order.creation.desc()) # Les billets les plus récents en premier
        )
        orders = result.scalars().all()
# 1. On récupère la date du jour calée à minuit pile (00:00:00)
        today_midnight = datetime.combine(datetime.now().date(), time.min)
        # 2. Requête 1 : Uniquement les événements "À la une" validés par l'admin
        featured_query = (
            select(Event)
            .where(
                Event.date >= today_midnight,
                Event.is_deleted == False,
                Event.is_featured == True  # 💡 FILTRE SUR TON CHAMP CLÉ
            )
            .order_by(Event.date.asc())
        )
        featured_res = await db.execute(featured_query)
        featured_events = featured_res.scalars().all()

        # 3. Requête 2 : Tous les événements à venir pour la liste générale
        upcoming_query = (
            select(Event)
            .where(
                Event.date >= today_midnight,
                Event.is_deleted == False
            )
            .order_by(Event.date.asc())
        )
        upcoming_res = await db.execute(upcoming_query)
        upcoming_events = upcoming_res.scalars().all()

        # 4. Formatage et retour des deux listes bien distinctes
        return {
            "featured_events": [
                {
                    "event_name": event.name,
                    "event_photo_url": event.photo_url,
                    "event_id": event.id,
                    "event_date": event.date.strftime("%d/%m/%Y") if isinstance(event.date, datetime) else str(event.date),
                    "location": event.location,
                    "remaining_seats": (event.total_capacity - event.sold_seats) if event.total_capacity else 0
                }
                for event in featured_events
            ],
            "upcoming_events": [
                {
                    "event_name": event.name,
                    "event_photo_url": event.photo_url,
                    "event_id": event.id,
                    "event_date": event.date.strftime("%d/%m/%Y") if isinstance(event.date, datetime) else str(event.date),
                    "location": event.location
                }
                for event in upcoming_events
            ]
        }
    except Exception as e:
        print(f"Erreur API Événements pour l'user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger la liste des événements pour le moment."
        )
@Root.get("/user/profile")
async def user_profil(
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'authentification via le cookie
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        # Si le participant n'est pas connecté, redirection flash vers la page de login
        request.session['invalid_number'] = "Veuillez vous connecter pour accéder à vos billets."
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    invalid_name = request.session.pop('invalid_name',None)
    try:
        # 2. Récupération de l'utilisateur pour afficher ses infos (optionnel mais pro)
        user_res = await db.execute(select(ExternalUser).where(ExternalUser.id == user_id))
        current_user = user_res.scalars().first()
        
        if not current_user:
            # Sécurité si le cookie contient un ID qui n'existe plus en BDD
            response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie("session_user_id")
            return response
        
    except Exception as e:
        print(f"Erreur lors du chargement de l'espace compte pour l'user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger vos billets pour le moment."
        )

    # 4. Envoi des données triées au template HTML
    return templates.TemplateResponse(
        "external_user/my_account/user_profile.html", 
        {
            "request": request, 
            "invalid_name_message":invalid_name,
            "current_user": current_user # les donnees des l'urilisateur
        }
    )

@Root.post("/user/profile/update")
async def update_profile(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'authentification via le cookie
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        request.session['invalid_number'] = "Veuillez vous connecter pour accéder à vos billets."
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
    # 2. Récupération de l'utilisateur (Correction de l'indentation ici)
    user_res = await db.execute(select(ExternalUser).where(ExternalUser.id == user_id))
    current_user = user_res.scalars().first()
        
    if not current_user:
        response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie("session_user_id")
        return response

    # 3. Nettoyage strict des inputs
    clean_name = name.strip()
    clean_phone = phone.strip()
    
    # Validation du nom
    if not clean_name or len(clean_name) < 2:
        request.session['invalid_name'] = "Veuillez entrer un nom valide."
        return RedirectResponse("/user/profile", status_code=303)

    # 4. SÉCURITÉ : Vérifier si le nouveau numéro est déjà utilisé par un AUTRE compte
    if clean_phone != current_user.phone_number: # (Remplace par .phone si c'est le vrai nom)
        phone_check = await db.execute(
            select(ExternalUser).where(
                ExternalUser.phone_number == clean_phone, 
                ExternalUser.id != user_id # On cherche quelqu'un d'autre que lui
            )
        )
        if phone_check.scalars().first():
            request.session['invalid_phone'] = "Ce numéro de téléphone est déjà associé à un autre compte."
            return RedirectResponse("/user/profile", status_code=303)

    # 5. Assignation des modifications sur l'objet SQLAlchemy chargé
    current_user.name = clean_name
    current_user.phone_number = clean_phone  # Ajusté selon tes routes précédentes
    
    # 6. Validation et sauvegarde asynchrone
    try:
        await db.commit()    # Valide la transaction en BDD
    except Exception as e:
        await db.rollback()  # Annulation en cas de pépin
        print(f"Erreur de mise à jour profil : {str(e)}") # Pratique pour le debug en console
        raise HTTPException(status_code=500, detail="Erreur lors de la mise à jour.")

    # 7. Redirection vers le dashboard
    return responses.RedirectResponse(url="/my_account", status_code=status.HTTP_303_SEE_OTHER)


@Root.get("/user/historique")
async def user_historique(
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'authentification via le cookie
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        # Si le participant n'est pas connecté, redirection flash vers la page de login
        request.session['invalid_number'] = "Veuillez vous connecter pour accéder à vos billets."
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    invalid_name = request.session.pop('invalid_name',None)
    try:
        # 2. Récupération de l'utilisateur pour afficher ses infos (optionnel mais pro)
        user_res = await db.execute(select(ExternalUser).where(ExternalUser.id == user_id))
        current_user = user_res.scalars().first()
        
        if not current_user:
            # Sécurité si le cookie contient un ID qui n'existe plus en BDD
            response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie("session_user_id")
            return response
        
        result = await db.execute(
            select(Order).where(Order.user_id == current_user.id) # on recupere ses commande deja payer
            .options(
                selectinload(Order.events),   # Jointure pour récupérer le titre/date de l'événement
                selectinload(Order.tickets)  # Jointure pour récupérer la liste des tickets associés
            )
            .order_by(Order.creation.desc()) # Les billets les plus récents en premier
        )
        orders = result.scalars().all()

    # 4. Envoi des données triées au template HTML
        return [
            {
                #"id": order.id,
                # On prend les 8 premiers caractères de l'ID en majuscule pour la Réf
                #"ref": order.id[:8].upper() if order.id else "INCONNU",
                # On récupère le nom de l'événement lié de manière sécurisée
                "event_name": order.events.name if order.events else "Événement sans nom",
                "event_photo_url":order.events.photo_url,
                "location":order.events.location
            }
            for order in orders
        ]
    except Exception as e:
        print(f"Erreur lors du chargement de l'espace compte pour l'user {user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger vos billets pour le moment."
        )

@Root.get("/user/register/form")#formulaire d'inscription pour un nouvel utilisateur
async def register_form(request: Request):
    invalid_username = request.session.pop('invalid_username', None)
    invalid_phone = request.session.pop('invalid_phone', None)
    invalid_password = request.session.pop('invalid_password', None)
    return templates.TemplateResponse("external_user/forms/register.html", {"request": request, "invalid_username": invalid_username, "invalid_phone": invalid_phone, "invalid_password": invalid_password})

@Root.post("/user/register")#route pour enregistrer un nouvel utilisateur
async def register_user(request: Request, username: str = Form(...), phone: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(connecting)):
    # 1. Nettoyage strict des inputs (Sécurité de base)
    clean_username = username.strip()
    clean_phone = format_to_drc_phone(phone.strip()) # formater le numero de telephone en format congolais
    clean_password = password.strip()

    # 2. Vérification des contraintes (ex: longueur minimale)
    if not clean_username or len(clean_username) < 2:
        request.session['invalid_username'] = "Veiller entrer un nom valid"
        return RedirectResponse(url="/user/register/form", status_code=status.HTTP_303_SEE_OTHER)

    if not clean_phone or len(clean_phone) < 10:
        request.session['invalid_phone'] = "Veiller entrer un numéro de téléphone valide a 10 chiffres"
        return RedirectResponse(url="/user/register/form", status_code=status.HTTP_303_SEE_OTHER)

    if not clean_password or len(clean_password) < 8:
        request.session['invalid_password'] = "Veiller entrer un mot de passe fort sécurisé (au moins 8 caractères)"
        return RedirectResponse(url="/user/register/form", status_code=status.HTTP_303_SEE_OTHER)

    # 3. Vérification si l'utilisateur existe déjà
    existing_user = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == clean_phone))
    if existing_user.scalars().first():
        request.session['invalid_phone'] = "Ce numéro de téléphone est déjà utilisé."
        return RedirectResponse(url="/user/register/form", status_code=status.HTTP_303_SEE_OTHER)
    try:
        hashed_password = hash_password(clean_password)  # hasher le mot de passe avant de le stocker
        # 4. Création du nouvel utilisateur
        new_user = ExternalUser(
            name=clean_username,
            phone_number=clean_phone,
            password=hashed_password  # Assurez-vous de hasher le mot de passe avant de le stocker
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        print(f"Nouvel utilisateur créé avec succès : {new_user.name} ({new_user.password})")  # Affiche le nom et le mot de passe hashé dans la console pour vérification
    except Exception as e:
        await db.rollback()
        print(f"Erreur lors de la création de l'utilisateur : {str(e)}")
        raise HTTPException(status_code=500, detail="Erreur lors de la création du compte.")
    # 5. Redirection vers la page de login avec un message de succès
    request.session['success_message'] = "Votre compte a été créé avec succès."
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

@Root.get("/auth/reset-password/user_number")
async def get_user_number(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    response =templates.TemplateResponse("external_user/forms/user_phone_number.html", {"request": request,'csrf_token':csrf_token})
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,          # Protection contre le vol de jeton par JS (Garder obligatoire)
        samesite="lax",       # Permet au cookie de transiter sur les navigations standards
        secure=set_secure_cookie,         # TRÈS IMPORTANT en local (False permet au cookie de passer sans HTTPS)
        path="/"
        
    )
    return response
# ==========================================
# 1. ENVOI DE L'OTP (Quand l'utilisateur clique sur "Mot de passe oublié")
# ==========================================
@Root.post("/auth/forgot-password/otp")
async def send_otp(
    request: Request,
    phone_input: str = Form(...),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    phone = format_to_drc_phone(phone_input.strip())
    
    # 1. Recherche de l'utilisateur
    res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone))
    user = res.scalars().first()
    
    # 2. Préparation du jeton CSRF (Valable pour tout le monde)
    csrf_token = secrets.token_urlsafe(32)
    request.session['csrf_token'] = csrf_token 
    
    request.session['success_message'] = "Un code de validation à 6 chiffres vous a été envoyé par SMS si le numéro est valide."
    request.session['reset_phone'] = phone 

    # Préparation de la réponse de redirection générique
    response = RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="fastapi-csrf-token",   
        value=csrf_token,
        httponly=True,
        samesite="lax",
        secure=set_secure_cookie,
        path="/"
    )

    # 3. Si l'utilisateur n'existe pas, on simule visuellement le même comportement
    if not user:
        return response

    # 🎲 Génération du code à 6 chiffres
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at_time = datetime.now() + timedelta(minutes=5)

    try:
        # 4. On vérifie s'il y a déjà une ligne OTP pour cet utilisateur
        otp_res = await db.execute(select(OTP).where(OTP.ext_user_id == user.id))
        existing_otp = otp_res.scalars().first()
        
        if existing_otp:
            # Si une ligne existe, on recycle la ligne en mettant à jour les infos
            existing_otp.code = otp_code
            existing_otp.expires_at = expires_at_time
            existing_otp.otp_attempts = 0
        else:
            # Si aucune ligne n'existe, on crée une nouvelle entrée
            new_otp = OTP(
                ext_user_id=user.id,
                code=otp_code,
                expires_at=expires_at_time,
                otp_attempts=0
            )
            db.add(new_otp)
            
        await db.commit()
        
        # 📲 Envoi du vrai SMS ici (Twilio, etc.)
        print(f"--- [SMS/WhatsApp easyInvite] --- Code OTP pour {phone} : {otp_code}")
        
    except Exception as e:
        await db.rollback()
        print(f"Erreur BDD OTP : {str(e)}") # Pour ton débuggage en console
        request.session['error_message'] = "Erreur technique, veuillez réessayer."
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)
        
    return response

@Root.get("/user/otp/form")#la root pour le formulaire de verification de l'otp
async def otp_form(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    success_message = request.session.pop('success_message', None)
    reset_phone = request.session.pop('reset_phone', None)
    request.session['user_phone'] = reset_phone
    error_message = request.session.pop('error_message', None)  
    response= templates.TemplateResponse("external_user/forms/otp_verification.html", {"request": request, "csrf_token": csrf_token, "success_message": success_message, "reset_phone": reset_phone, "error_message": error_message})
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,
        samesite="lax",
        secure=set_secure_cookie,
        path="/"
    )
    return response

# ==========================================
# 2. VÉRIFICATION DE L'OTP
# ==========================================
@Root.post("/auth/verify-otp") # 👈 URL pour la verification de l'otp
async def verify_otp(
    request: Request,
    otp_input: str = Form(...),  
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    # 1. Récupération sécurisée du téléphone (Correction du bug potentiel sur None)
    phone = request.session.get('user_phone')
    if not phone:
        request.session['reset_phone'] = phone
        request.session['error_message'] = "Session expirée ou invalide. Veuillez recommencer."
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)
        
    formated_phone = format_to_drc_phone(phone.strip())

    # 2. Recherche de l'utilisateur
    res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == formated_phone))
    user = res.scalars().first()
    
    if not user :
        request.session['error_message'] = "Aucun code demandé pour ce numéro."
        request.session['reset_phone'] = phone
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)
    otp_res = await db.execute(select(OTP).where(OTP.ext_user_id ==user.id))
    user_otp = otp_res.scalars().first()
    if not user_otp:
        request.session['error_message'] = "Aucun code OTP trouvé pour cet utilisateur."
        request.session['reset_phone'] = phone
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)
    
    # 4. Sécurité anti-brute force
    if user_otp.otp_attempts >= 3:
        request.session['error_message'] = "Trop de tentatives infructueuses. Demandez un nouveau code."
        request.session['reset_phone'] = phone
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)

    # 5. Vérification de l'expiration
    if user_otp.expires_at < datetime.now():
        request.session['error_message'] = "Le code OTP a expiré (valide 5 min)."
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)    
    # 6. Vérification du code saisi
    
    if user_otp.code != otp_input.strip():
        user_otp.otp_attempts += 1 
        await db.commit()
        request.session['reset_phone'] = phone
        request.session['error_message'] = f"Code OTP incorrect. Il vous reste {3 - user_otp.otp_attempts} essais."
        return RedirectResponse(url="/user/otp/form", status_code=status.HTTP_303_SEE_OTHER)

    # 🎉 LE CODE EST BON ! On finalise la transaction de sécurité directement ici
    # Redirection vers la page de modification du mot de passe 
    request.session['user_phone'] = phone
    request.session['otp_verified'] = True  # 👈 LA CLÉ DE SÉCURITE
    response = RedirectResponse(url="/user/reset_password", status_code=status.HTTP_303_SEE_OTHER)   
    return response

@Root.post("/auth/forgot_password")#la modification du mot de passe oublier d'un utilisateur deja inscrit
async def forgot_password(
    request: Request,
    phone_input: str = Form(...),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    # Nettoyage et formatage strict du numéro (ex: 243...)
    phone = format_to_drc_phone(phone_input.strip())
    
    # Recherche de l'utilisateur
    res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone))
    user = res.scalars().first()
    
    # 🚨 Sécurité : Même si l'utilisateur n'existe pas, on affiche un message générique
    # pour éviter que les pirates sachent quels numéros sont inscrits.
    if not user:
        request.session['success_message'] = "Si ce numéro existe, un lien de réinitialisation vous a été envoyé."
        return RedirectResponse(url="/auth/forgot-password/form", status_code=status.HTTP_303_SEE_OTHER)

    # Génération d'un token sécurisé unique et aléatoire
    token = secrets.token_urlsafe(32)
    
    # Définition de l'expiration (Valide pendant 15 minutes)
    expiration_time = datetime.now() + timedelta(minutes=15)
    
    # Mise à jour de l'utilisateur en BDD
    user.reset_token = token
    user.reset_token_expires = expiration_time
    
    try:
        await db.commit()
        
        # ✉️ ICI : Tu envoies le lien par SMS ou via un service tiers.
        # Le lien ressemblera à : /auth/reset-password/form?token=LE_TOKEN
        print(f"--- SIMULATION ENVOI --- Link: http://localhost:8000/auth/reset-password/form?token={token}")
        
    except Exception as e:
        await db.rollback()
        request.session['error_message'] = "Une erreur est survenue, veuillez réessayer."
        return RedirectResponse(url="/auth/forgot-password/form", status_code=status.HTTP_303_SEE_OTHER)

    request.session['success_message'] = "Un lien de réinitialisation vous a été envoyé."
    
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)


@Root.get("/user/reset_password")
async def reset_password_page(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse(
        "external_user/forms/reset_password.html", 
        {
            "request": request,
            "csrf_token": csrf_token
        }
    )
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,
        samesite="lax",
        secure=set_secure_cookie,
        path="/"
    )
    return response

# ==========================================
# 2. SOUMISSION DU NOUVEAU MOT DE PASSE
# ==========================================
@Root.post("/auth/reset-password")
async def reset_password(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    user_phone = request.session.get('user_phone')
    is_otp_verified = request.session.get('otp_verified') # 👈 On récupère le badge de sécurité
    
    # 🚨 SÉCURITÉ : Si le badge n'est pas True, redirection immédiate !
    if not user_phone or is_otp_verified is not True:
        request.session['error_message'] = "Action non autorisée ou session expirée. Veuillez recommencer."
        return RedirectResponse(url="/auth/forgot-password/form", status_code=status.HTTP_303_SEE_OTHER)
    formated_phone = format_to_drc_phone(user_phone.strip())
    # 1. Vérifications de base
    if new_password != confirm_password:
        request.session['error_message'] = "Les deux mots de passe ne correspondent pas."
        return RedirectResponse(url=f"/auth/reset-password/form", status_code=status.HTTP_303_SEE_OTHER)
        
    if len(new_password) < 8:
        request.session['error_message'] = "Le mot de passe doit contenir au moins 8 caractères."
        return RedirectResponse(url=f"/auth/reset-password/form", status_code=status.HTTP_303_SEE_OTHER)

    # 2. Chercher l'utilisateur possédant ce token
    res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == formated_phone))
    user = res.scalars().first()

    # 3. Vérifier si le token existe et s'il n'est pas expiré
    if not user :
        request.session['error_message'] = "Le lien de réinitialisation est invalide ou a expiré."
        return RedirectResponse(url="/auth/forgot-password/form", status_code=status.HTTP_303_SEE_OTHER)
    get_otp_res = await db.execute(select(OTP).where(OTP.ext_user_id == user.id))
    user_otp = get_otp_res.scalars().first()
    if not user_otp:
        request.session['error_message'] = "Le lien de réinitialisation est invalide ou a expiré."
        return RedirectResponse(url="/auth/forgot-password/form", status_code=status.HTTP_303_SEE_OTHER)
    # 4. Appliquer le nouveau mot de passe haché
    try:
        user.password = hash_password(new_password.strip())
        
        # 🚨 TRÈS IMPORTANT : On détruit le token pour qu'il ne puisse plus être réutilisé
        user_otp.code = None
        user_otp.expires_at = None
        user_otp.otp_attempts = 0
        
        await db.commit()
        # 🌟 AJOUTE CES DEUX LIGNES ICI POUR TOUT NETTOYER :
        request.session.pop('user_phone', None)
        request.session.pop('otp_verified', None)
    except Exception as e:
        await db.rollback()
        request.session['error_message'] = "Erreur interne lors de la mise à jour."
        return RedirectResponse(url=f"/auth/reset-password/form", status_code=status.HTTP_303_SEE_OTHER)

    request.session['success_update_message'] = "Votre mot de passe a été modifié avec succès. Connectez-vous !"
    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)

@Root.get("/auth/login")
async def login_page(request: Request, db: AsyncSession = Depends(connecting)):
    # 1. Récupération du message d'erreur flash (ex: numéro invalide)
    invalid_phone_number = request.session.pop('invalid_number', None)
    invalid_user = request.session.pop('invalid_user', None)
    csrf_token = secrets.token_urlsafe(32)
    # 2. Vérification si l'utilisateur possède déjà un cookie de session
    current_user_id = request.cookies.get("session_user_id")
    success_message = request.session.pop('success_message', None)
    success_update_message = request.session.pop('success_update_message', None)
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
    response = templates.TemplateResponse(
        "external_user/forms/login.html", # 🎯 Utilise ton template de formulaire de login ici !
        {
            "request": request, 
            "invalid_phone_number": invalid_phone_number,
            'csrf_token':csrf_token,
            'success_message': success_message,
            "invalid_user": invalid_user,
            "success_update_message": success_update_message
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

@Root.get("/auth/verify-otp-page")
async def verify_otp_page(request: Request, phone: str):
    """
    Cette route intercepte le GET du navigateur après la génération de l'OTP.
    L'URL ressemblera à : http://127.0.0.1:8000/auth/verify-otp-page?phone=243991635198
    """
    # On renvoie le fichier HTML en lui passant le numéro de téléphone.
    # Ainsi, Jinja2 pourra l'afficher à l'écran et l'injecter dans le champ caché <input type="hidden">
    incorect_otp = request.session.pop('incorrect_otp',None)
    csrf_token = secrets.token_urlsafe(32)
    response= templates.TemplateResponse(
        "external_user/forms/verify_otp.html", 
        {
            "request": request, 
            "phone": phone,
            "incorrect_otp_message":incorect_otp,
            "csrf_token":csrf_token
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

@Root.post("/ext_user/login")
async def verify_user(
    request: Request,
    form_data:OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    # 1. Récupérer l'utilisateur correspondant au numéro
    user_name = form_data.username
    password = form_data.password
    
    # 1. Nettoyage du numéro de téléphone (uniquement les chiffres)
    phone =format_to_drc_phone(user_name.strip())
    
    # 2. Requête en base de données
    res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone))
    user = res.scalars().first()
    
    # 3. Sécurité : Message d'erreur identique pour le numéro ET le mot de passe
    error_message = "Numéro de téléphone ou mot de passe incorrect."

    if not user:
        request.session['invalid_user'] = error_message
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)

    if not verify_password(password, user.password):
        request.session['invalid_user'] = error_message
        return RedirectResponse("/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
    # 4. AUTHENTIFICATION & REDIRECTION 🎉
    response = RedirectResponse(url="/my_account", status_code=status.HTTP_303_SEE_OTHER)
    # 4. AUTHENTIFICATION & REDIRECTION 🎉
    response = RedirectResponse(url="/my_account", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_user_id", value=user.id, httponly=True)
    
    return response

@Root.get("/user/auth/logout")
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
