from datetime import datetime, time
import re
from fastapi import APIRouter, Request, Form,Query,Depends,Cookie,HTTPException,status,responses
from fastapi.responses import HTMLResponse, RedirectResponse,Response ,StreamingResponse,JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles 
from fastapi.templating import Jinja2Templates  
from requests import request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc,delete
from sqlalchemy.orm import selectinload
from db_setting import connecting
from config import secret, algo,REDIS_SETTINGS,set_secure_cookie,verify_csrf
import jwt,random,io,secrets,urllib
from models import Organizer, Ticket_price, User, Order, Event,ExternalUser,OTP,Ticket
from app.security.permissions import permission_required
from datetime import datetime, timedelta,timezone,date
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
    orders_query = select(Event).where(Event.type == "other", Event.is_deleted == False).options(selectinload(Event.ticket_prices))\
        .order_by(desc(Event.created_date))\
        .offset(offset)\
        .limit(per_page)
    events = (await db.execute(orders_query)).scalars().all()
    query = select(Event).where(Event.type == "other",Event.is_featured == True,Event.is_deleted == False).options(selectinload(Event.ticket_prices))\
        .order_by(desc(Event.created_date))\
        .offset(offset)\
        .limit(per_page)
    featured_events = (await db.execute(query)).scalars().all()
    
    maintenant = datetime.now()
    for event in events:
        # On crée une variable à la volée sur l'objet Event
        event.is_past = event.date < maintenant
    
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
                Event.is_deleted == False,
                Event.type == "other"  # FILTRE SUR TON CHAMP CLÉ
            )
            .order_by(Event.date.asc())
        )
        upcoming_res = await db.execute(upcoming_query)
        upcoming_events = upcoming_res.scalars().all()#les evenements avenir pour la liste generale dans le compte du participant

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

# Autorise les lettres, espaces, tirets et accents pour le nom (min 2 caractères)
NAME_REGEX = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ\s\'-]{2,50}$")
# Autorise uniquement les chiffres (entre 8 et 15 chiffres, ex: 243XXXXXXXXX)
PHONE_REGEX = re.compile(r"^\d{8,15}$")
@Root.post("/user/update-profile")
async def update_profile(
    request: Request,
    user_name: str = Form(...),
    user_phone: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(connecting)
):
    # 1. Sécurité d'authentification : Vérification de la session active
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Votre session a expiré. Veuillez vous reconnecter."}
        )

    # 2. Nettoyage et Normalisation des données entrantes
    clean_name = " ".join(user_name.strip().split())  # Supprime les espaces doubles internes
    clean_phone = user_phone.strip().replace(" ", "").replace("+", "") # Supprime les espaces et le +

    # 3. Validation de Production (Data Integrity)
    if not NAME_REGEX.match(clean_name):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "Le nom complet est invalide ou contient des caractères non autorisés."}
        )
        
    if not PHONE_REGEX.match(clean_phone):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error": "Le numéro de téléphone doit contenir uniquement des chiffres (entre 8 et 15)."}
        )

    try:
        # 4. Récupération sécurisée de l'utilisateur
        user_res = await db.execute(select(ExternalUser).where(ExternalUser.id == user_id))
        current_user = user_res.scalars().first()

        if not current_user:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={"error": "Utilisateur introuvable."}
            )

        # 5. Sécurité Critique : Vérification cryptographique du mot de passe
        if not verify_password(password, current_user.password):
            # En prod, tu devrais enregistrer cette tentative échouée pour détecter les attaques
            print(f"[SECURITY ALERT] Échec de vérification de mot de passe pour l'utilisateur ID: {user_id}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED, # Code 401 plus précis pour un échec d'auth
                content={"error": "Mot de passe actuel incorrect. Action refusée."}
            )

        # 6. Contrainte d'unicité sur le numéro de téléphone
        if clean_phone != current_user.phone_number:
            phone_check = await db.execute(
                select(ExternalUser).where(ExternalUser.phone_number == clean_phone, ExternalUser.id != user_id)
            )
            if phone_check.scalars().first():
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT, # Code 409 (Conflict) idéal pour les doublons
                    content={"error": "Ce numéro de téléphone est déjà associé à un autre compte."}
                )

        # 7. Persistance sécurisée des données
        current_user.name = clean_name
        current_user.phone_number = clean_phone
        
        db.add(current_user)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback() # Sécurité maximale : on annule si le commit crash
            print(f"[PROD CRITICAL ERROR] Échec du commit SQL : {str(e)}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Une erreur technique est survenue lors de l'enregistrement."}
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Votre profil a été mis à jour avec succès !"}
        )

    except Exception as e:
        # En cas de crash inattendu (ex: coupure BDD), on rollback immédiatement la transaction SQL
        await db.rollback()
        # Log de production anonymisé (on ne logge jamais les infos sensibles comme le password ou le numéro)
        print(f"[PROD CRITICAL ERROR] Erreur lors de la mise à jour du profil de l'utilisateur {user_id}: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Une erreur technique est survenue. Veuillez réessayer plus tard."}
        )

@Root.get("/user/historique")
async def user_historique(
    request: Request, 
    db: AsyncSession = Depends(connecting)
):
    # 1. Sécurité de session
    user_id = request.cookies.get("session_user_id")
    if not user_id:
        request.session['invalid_number'] = "Veuillez vous connecter pour accéder à vos billets."
        return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
        
    request.session.pop('invalid_name', None)
    
    try:
        # 2. Récupération de l'utilisateur
        user_res = await db.execute(select(ExternalUser).where(ExternalUser.id == user_id))
        current_user = user_res.scalars().first()
        
        if not current_user:
            response = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie("session_user_id")
            return response
        
        # 3. Requête SQL
        result = await db.execute(
            select(Order)
            .where(Order.user_id == current_user.id)
            .options(selectinload(Order.events))
            .order_by(Order.creation.desc())
        )
        orders = result.scalars().all()

        today = date.today()

        # 4. Filtrage et formatage (Avec la correction .date() pour la comparaison)
        return [
            {
                "event_name": order.events.name if order.events else "Événement sans nom",
                "location": order.events.location if order.events else "Lieu non spécifié",
                "event_date": order.events.date.strftime("%d/%m/%Y") if order.events and order.events.date else "Date inconnue"
            }
            for order in orders
            # 💡 FIX PROD : On ajoute .date() pour convertir le datetime en date pure avant la comparaison
            if order.events and order.events.date and order.events.date.date() < today
        ]
        
    except Exception as e:
        print(f"[ERROR] Échec de l'historique pour l'utilisateur {user_id} : {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger votre historique pour le moment."
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
@Root.post("/auth/forgot_password")
async def forgot_password(
    request: Request,
    phone_input: str = Form(...),
    user_type: str = Form(...),
    db: AsyncSession = Depends(connecting),
    _ = Depends(verify_csrf)
):
    phone_clean = format_to_drc_phone(phone_input.strip())
    user_found = None
    
    try:
        # 1. Recherche de l'utilisateur selon son type
        if user_type == "organizer":
            res = await db.execute(select(Organizer).where(Organizer.phone_number == phone_clean))
            user_found = res.scalars().first()
        else:
            res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone_clean))
            user_found = res.scalars().first()

        # SÉCURITÉ : Réponse identique même si le compte n'existe pas (Anti-Énumération)
        if not user_found:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"message": "Si ce numéro existe, un code OTP de réinitialisation vous a été envoyé."}
            )

        # 2. Nettoyage initial : On supprime les anciens OTP de cet utilisateur pour éviter les conflits
        if user_type == "organizer":
            await db.execute(delete(OTP).where(OTP.organizer_id == user_found.id))
        else:
            await db.execute(delete(OTP).where(OTP.ext_user_id == user_found.id))
            
        # 3. Génération cryptographique de l'OTP à 6 chiffres
        otp_code = str(secrets.randbelow(900000) + 100000)
        expiration_time = datetime.now() + timedelta(minutes=5) # Valide 5 minutes
        
        # 4. 💾 Insertion dans la classe OTP
        nouvel_otp = OTP(
            code=otp_code,
            expires_at=expiration_time,
            otp_attempts=0,
            ext_user_id=user_found.id if user_type != "organizer" else None,
            organizer_id=user_found.id if user_type == "organizer" else None
        )
        db.add(nouvel_otp)
        await db.commit()
        
        # 5. Stockage des variables pivots dans la session chiffrée du navigateur
        request.session['reset_user_phone'] = str(phone_clean)
        request.session['reset_user_type'] = str(user_type)
        
        # Simulation de l'envoi du SMS (Log console)
        print(f"--- 💬 SMS OTP ENVOI A ({phone_clean}) ({user_type}) --- Code : {otp_code} (Valide 5 min)")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Un code de vérification OTP vous a été envoyé par SMS."}
        )

    except Exception as e:
        await db.rollback()
        print(f"🚨 Erreur lors de la génération de l'OTP : {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Une erreur interne est survenue."}
        )

@Root.get("/user/otp/form")#la root pour le formulaire de verification de l'otp
async def otp_form(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    success_message = request.session.pop('success_message', None)
    reset_phone = request.session.get('reset_phone', None)
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
@Root.post("/auth/verify-otp")
async def verify_otp(
    request: Request, 
    otp_input: str = Form(...), 
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de la session navigateur
    phone = request.session.get('reset_user_phone')
    user_type = request.session.get('reset_user_type')

    if not phone or not user_type:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"status": "SESSION_EXPIRED", "detail": "Votre session a expiré. Veuillez recommencer la demande."}
        )

    try:
        # 2. Récupération de l'utilisateur pour lier l'ID
        if user_type == "organizer":
            res_user = await db.execute(select(Organizer).where(Organizer.phone_number == phone))
        else:
            res_user = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone))
            
        user_found = res_user.scalars().first()
        if not user_found:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, 
                content={"status": "USER_NOT_FOUND", "detail": "Compte introuvable."}
            )

        # 3. Récupération de l'OTP actif associé dans la table `otps`
        if user_type == "organizer":
            res_otp = await db.execute(select(OTP).where(OTP.organizer_id == user_found.id))
        else:
            res_otp = await db.execute(select(OTP).where(OTP.ext_user_id == user_found.id))
            
        db_otp = res_otp.scalars().first()
        if not db_otp:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, 
                content={"status": "NO_ACTIVE_OTP", "detail": "Aucun code OTP actif trouvé. Veuillez refaire une demande."}
            )

        # 🛡️ SÉCURITÉ 1 : Limite de tentatives (Max 3)
        if db_otp.otp_attempts >= 3:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, 
                content={"status": "OTP_BLOCKED", "detail": "Ce code a été suspendu suite à trop de tentatives infructueuses."}
            )

        # 🛡️ SÉCURITÉ 2 : Validation du temps (Strictement en UTC pour la prod)
        if datetime.now(timezone.utc) > db_otp.expires_at.replace(tzinfo=timezone.utc):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, 
                content={"status": "OTP_EXPIRED", "detail": "Le code OTP a expiré (limite de 5 minutes dépassée)."}
            )

        # 🛡️ SÉCURITÉ 3 : Confrontation du code
        if db_otp.code != otp_input.strip():
            db_otp.otp_attempts += 1
            await db.commit()
            
            essais_restants = max(0, 3 - db_otp.otp_attempts)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST, 
                content={
                    "status": "INVALID_CODE", 
                    "detail": "Code OTP incorrect.",
                    "attempts_left": essais_restants
                }
            )

        # 🟢 SUCCÈS : Le code est bon ! On le consomme immédiatement (destruction BDD)
        await db.delete(db_otp)
        
        # 🔑 Génération d'un token sécurisé à usage unique pour l'Étape Finale
        reset_token = secrets.token_urlsafe(32)
        
        # Stockage du token et de son expiration en session
        request.session['reset_token'] = reset_token
        request.session['reset_token_expires'] = (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()
        await db.commit()

        # On renvoie le token au frontend (ton JS pourra le stocker ou l'inclure dans l'URL/Formulaire final)
        return JSONResponse(
            status_code=status.HTTP_200_OK, 
            content={
                "status": "SUCCESS", 
                "detail": "Code vérifié avec succès.",
                "reset_token": reset_token
            }
        )

    except Exception as e:
        await db.rollback()
        print(f"🚨 [PROD ERROR] verify_otp : {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "SERVER_ERROR", "detail": "Une erreur interne est survenue."}
        )

@Root.get("/user/reset_password")
async def reset_password_page(request: Request,token: str =Query(...)):
    csrf_token = secrets.token_urlsafe(32)
    session_token = request.session.get('reset_token')
    token_expires = request.session.get('reset_token_expires')

    # 🛡️ Barrière 1 : Session vide
    if not session_token or not token_expires:
        return RedirectResponse(url="/auth/forgot_password?error=Session+invalide", status_code=status.HTTP_303_SEE_OTHER)

    # 🛡️ Barrière 2 : Le token de l'URL ne correspond pas à la session
    if token.strip() != session_token:
        return RedirectResponse(url="/auth/forgot_password?error=Jeton+invalide", status_code=status.HTTP_303_SEE_OTHER)

    # 🛡️ Barrière 3 : Expiration temporelle
    current_timestamp = datetime.now(timezone.utc).timestamp()
    if current_timestamp > token_expires:
        request.session.pop('reset_token', None)
        request.session.pop('reset_token_expires', None)
        return RedirectResponse(url="/auth/forgot_password?error=Le+delai+est+depasse", status_code=status.HTTP_303_SEE_OTHER)
    response = templates.TemplateResponse(
        "external_user/forms/reset_password.html", 
        {
            "request": request,
            "csrf_token": csrf_token,
            "reset_token": session_token  # On renvoie le token pour l'inclure dans le formulaire final
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
# 2. SOUMISSION DU NOUVEAU MOT DE PASSE new_password: str = Form(...),
    confirm_password: str = Form(...),
# ==========================================

@Root.post("/auth/reset-password-form")
async def reset_password_final(
    request: Request,
    token_input: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(connecting),
    _ = Depends(verify_csrf)
):
    # 1. Extraction des preuves depuis la session
    session_token = request.session.get('reset_token')
    token_expires = request.session.get('reset_token_expires')
    phone = request.session.get('reset_user_phone')  # 💡 Harmonisé
    user_type = request.session.get('reset_user_type')

    # 🛡️ BARRIÈRE 1 : Absence de session de réinitialisation
    if not session_token or not token_expires or not phone or not user_type:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, 
            content={"status": "UNAUTHORIZED", "detail": "Action interdite. Veuillez recommencer le processus."}
        )

    # 🛡️ BARRIÈRE 2 : Vérification de la correspondance des tokens
    if token_input.strip() != session_token:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN, 
            content={"status": "INVALID_TOKEN", "detail": "Jeton de réinitialisation invalide."}
        )

    # 🛡️ BARRIÈRE 3 : Vérification du timeout du token (5 minutes max après validation OTP)
    if datetime.now(timezone.utc).timestamp() > token_expires:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"status": "TOKEN_EXPIRED", "detail": "Le délai pour modifier votre mot de passe est dépassé."}
        )

    # 🛡️ BARRIÈRE 4 : Validation et confrontation des mots de passe
    if new_password != confirm_password:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"status": "PASSWORD_MISMATCH", "detail": "Les deux mots de passe ne correspondent pas."}
        )
        
    if len(new_password) < 8:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST, 
            content={"status": "PASSWORD_TOO_WEAK", "detail": "Le mot de passe doit contenir au moins 8 caractères."}
        )

    try:
        # 2. Recherche de l'utilisateur concerné
        if user_type == "organizer":
            res = await db.execute(select(Organizer).where(Organizer.phone_number == phone))
            user = res.scalars().first()
        else:
            res = await db.execute(select(ExternalUser).where(ExternalUser.phone_number == phone))
            user = res.scalars().first()

        if not user:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND, 
                content={"status": "USER_LOST", "detail": "Utilisateur introuvable."}
            )

        # 3.  Mise à jour sécurisée du mot de passe
        user.password = hash_password(new_password) 
        
        #  NETTOYAGE CRUCIAL DE PROD : On nettoie TOUTES les clés de session utilisées
        request.session.pop('reset_user_phone', None)  # Correctement nettoyé ici
        request.session.pop('reset_user_type', None)
        request.session.pop('reset_token', None)
        request.session.pop('reset_token_expires', None)
        request.session.pop('otp_verified', None)  # Optionnel : nettoie aussi le flag d'état si présent
        
        await db.commit()

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "PASSWORD_CHANGED", "detail": "Votre mot de passe a été modifié avec succès. Vous pouvez vous connecter."}
        )

    except Exception as e:
        await db.rollback()
        print(f"🚨 [PROD ERROR] reset_password_final : {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            content={"status": "SERVER_ERROR", "detail": "Erreur lors de la mise à jour du mot de passe."}
        )
    
@Root.get("/auth/login")
async def login_page(request: Request, db: AsyncSession = Depends(connecting)):
    # 1. Récupération du message d'erreur flash (ex: numéro invalide)
    invalid_phone_number = request.session.pop('invalid_number', None)
    invalid_user = request.session.pop('invalid_user', None)
    csrf_token = secrets.token_urlsafe(32)
    # 2. Vérification si l'utilisateur possède déjà un cookie de session
    current_user_id = request.cookies.get("session_user_id",None)
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
