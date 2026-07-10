from urllib import request

from fastapi import APIRouter,Request,Form,Depends,HTTPException,status
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import RedirectResponse,HTMLResponse,JSONResponse
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from db_setting import connecting
from models import Organizer,Event
from Routers.loging import hash_password,verify_password
from Routers.guest import format_to_drc_phone
from config import verify_csrf,set_secure_cookie
import secrets
from datetime import datetime

Root = APIRouter()
templates = Jinja2Templates(directory = "Templates")
@Root.get("/organizer/account", name="organizer_dashboard", response_class=HTMLResponse)
async def organisar_dashboard(
    request: Request,
    db: AsyncSession = Depends(connecting)
):
    # 💡 CORRECTIF MAJEUR : Récupération depuis la session (aligné avec le reste de l'auth)
    current_organizer_id = request.session.get("session_user_id")
    
    if not current_organizer_id:
        # Si l'organisateur n'est pas connecté, redirection avec message flash
        request.session['invalid_number'] = "Veuillez vous connecter pour accéder à votre espace."
        return RedirectResponse(url="/organizer/sign-in", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        # 1. Récupération de l'organisateur pour valider qu'il existe toujours
        organizer_res = await db.execute(select(Organizer).where(Organizer.id == current_organizer_id))
        current_organizer = organizer_res.scalars().first()
        
        if not current_organizer:
            # Sécurité : Si l'ID en session n'existe plus en BDD (ex: compte supprimé)
            request.session.clear() # On nettoie la session invalide
            request.session['invalid_user'] = "Compte introuvable. Veuillez vous reconnecter."
            return RedirectResponse(url="/organizer/sign-in", status_code=status.HTTP_303_SEE_OTHER)
 
        # 2. Récupération de ses événements non supprimés
        # Utilisation de Event.date_fin pour la cohérence temporelle
        query = select(Event).where(
            Event.organizer_id == current_organizer_id, 
            Event.is_deleted == False
        ).order_by(Event.date.desc())
        
        result = await db.execute(query)
        all_events = result.scalars().all()
        
        # 3. Séparation chronologique
        maintenant = datetime.now()
        active_events = [e for e in all_events if e.date >= maintenant]
        past_events = [e for e in all_events if e.date < maintenant]
        
        # 4. Logique des compteurs (Simulée pour l'instant)
        active_revenue = 450.00         
        total_sold_tickets = 124        
        total_historical_revenue = 2980.00 
        
        # 💡 CORRECTIF SCOPE : Le rendu du template se fait directement ici, dans le succès du bloc try
        return templates.TemplateResponse("e-ticket/organizer/dashboard.html", {
            'request': request,
            'current_organizer': current_organizer,
            "company_name": current_organizer.company_name or "Mon Agence Événementielle",
            "active_events": active_events,
            "past_events": past_events,
            "active_revenue": active_revenue,
            "total_sold_tickets": total_sold_tickets,
            "total_historical_revenue": total_historical_revenue
        })

    except Exception as e:
        # Log de l'erreur côté serveur
        print(f"Erreur lors du chargement de l'espace compte pour l'organizer {current_organizer_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Impossible de charger votre tableau de bord pour le moment."
        )

#====================organizer acount management
@Root.get("/organizer/sign-up", response_class=HTMLResponse)
async def get_register_page(
    request: Request):
    # 1. Génération d'un jeton CSRF unique et aléatoire
    csrf_token = secrets.token_urlsafe(32)
    # 2. Envoi du jeton au template HTML
    response = templates.TemplateResponse(
        "e-ticket/organizer/forms/account/sign_up.html", 
        {
            "request": request,
            "csrf_token": csrf_token,
        }
    )
    
    # 3. Stockage du jeton dans un cookie sécurisé (HttpOnly) pour la vérification future
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,        # Empêche le vol du jeton via un script JS malveillant
        samesite="lax",       # Protection standard pour les navigations web
        secure=set_secure_cookie, # Obligatoire en HTTPS (Prod)
        path="/"
    )
    
    return response

@Root.post("/organizer/register")
async def register_organizer(
    request: Request,
    company_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...,min_length=8),# 🔒 Sécurité : 8 caractères minimum requis !
    csrf_token: str = Form(...),          
    db: AsyncSession = Depends(connecting),
    _ = Depends(verify_csrf)               
):
    # Nettoyage des données
    email_clean = email.strip().lower()
    phone_clean = format_to_drc_phone(phone.strip())

    try:
        # 🛡️ SÉCURITÉ 1 : Vérifier l'email (Correction de l'attribut si nécessaire)
        email_check = await db.execute(select(Organizer).where(Organizer.email == email_clean))
        if email_check.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cette adresse email est déjà associée à un compte."
            )

        # 🛡️ SÉCURITÉ 2 : Vérifier le téléphone -> Utilisation de .phone_number (ton vrai attribut de modèle)
        phone_check = await db.execute(select(Organizer).where(Organizer.phone_number == phone_clean))
        if phone_check.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ce numéro de téléphone est déjà utilisé."
            )

        # Hachage sécurisé du mot de passe
        hashed_pwd = hash_password(password)
        
        # Création du nouvel organisateur avec les attributs EXACTS de ton modèle de BDD
        new_organizer = Organizer(
            company_name=company_name.strip(),
            email=email_clean,
            phone_number=phone_clean,                
            password=hashed_pwd,       
            is_active=True,
            is_verified=False
        )

        db.add(new_organizer)
        await db.commit()
        await db.refresh(new_organizer)

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={"message": "Votre compte organisateur a été créé avec succès !"}
        )

    # 💡 On intercepte les HTTPException pour qu'elles passent normalement sans déclencher le 500
   # 💡 Remplacer les anciens blocs 'except' par celui-ci :
    except HTTPException as http_err:
        # En cas d'erreur métier (Email/Tel déjà pris), on renvoie un JSON direct.
        # Cela évite le crash interne et donne exactement ce que le JavaScript attend !
        return JSONResponse(
            status_code=http_err.status_code,
            content={"detail": http_err.detail}
        )

    except Exception as e:
        await db.rollback()
        print(f"Erreur critique inscription : {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Une erreur interne est survenue sur le serveur."}
        )
    
@Root.get("/organizer/sign-in", response_class=HTMLResponse)
async def get_register_page(
    request: Request,
    db: AsyncSession = Depends(connecting),
    set_secure_cookie: bool = True # Idéalement géré par tes variables d'environnement
):
    # 1. Nettoyage de la clé de session (suppression de l'espace initial)
    current_user_id = request.session.get("session_user_id", None)
    
    # 2. Récupération et suppression immédiate des messages flash
    invalid_phone_number = request.session.pop('invalid_number', None)
    invalid_user = request.session.pop('invalid_user', None)
    success_message = request.session.pop('success_message', None)
    success_update_message = request.session.pop('success_update_message', None)
    invalid_session = request.session.pop('invalid_session', None) # Pour afficher le message d'expiration

    if current_user_id:
        try:
            result = await db.execute(select(Organizer).where(Organizer.id == current_user_id))
            user = result.scalars().first()
            
            if user:
                # Session valide -> Redirection vers le compte
                return RedirectResponse("/organizer/account", status_code=status.HTTP_303_SEE_OTHER)
            
            # 💡 CORRECTIF BOUCLE : La session contient un ID invalide, on nettoie TOUT sans rediriger
            request.session.clear() 
            invalid_session = "Votre session a expiré, veuillez vous reconnecter."
            
        except Exception as e:
            # En cas de problème BDD (ex: timeout), log propre
            # Utilise un vrai logger en prod à la place de print() si possible
            print(f"Erreur vérification user au login: {str(e)}")
            request.session.clear()
            response = RedirectResponse(url="/organizer/sign-in", status_code=status.HTTP_303_SEE_OTHER)
            response.delete_cookie("session_user_id")
            return response

    # 3. Génération du token CSRF pour le nouveau formulaire
    csrf_token = secrets.token_urlsafe(32)

    response = templates.TemplateResponse(
        "e-ticket/organizer/forms/account/login.html", 
        {
            "request": request,
            "csrf_token": csrf_token,
            "invalid_phone_number": invalid_phone_number,
            "success_message": success_message,
            "invalid_user": invalid_user,
            "success_update_message": success_update_message,
            "invalid_session": invalid_session
        }
    )
    
    # 4. Enregistrement sécurisé du Cookie CSRF
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,
        samesite="lax",
        secure=set_secure_cookie, # True en Prod, False en Local Dev
        path="/"
    )
    
    return response

@Root.post("/organizer/login")
async def verify_user(
    request: Request,
    csrf_token: str = Form(...),
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(connecting),
    _ = Depends(verify_csrf) # Sécurité CSRF au top
):
    user_name = form_data.username
    password = form_data.password
    
    # 1. Nettoyage du numéro de téléphone
    phone = format_to_drc_phone(user_name.strip())
    
    # 2. Requête en base de données (Vérifie bien tes attributs de modèle !)
    res = await db.execute(select(Organizer).where(Organizer.phone_number == phone))
    user = res.scalars().first()
    
    # 3. Message d'erreur uniforme (Top pour la sécurité)
    error_message = "Numéro de téléphone ou mot de passe incorrect."

    if not user:
        request.session['invalid_user'] = error_message
        return RedirectResponse("/organizer/sign-in", status_code=status.HTTP_303_SEE_OTHER)

    # 4. Vérification du mot de passe haché (Attribut cohérent : hashed_password)
    if not verify_password(password, user.password):
        request.session['invalid_user'] = error_message
        return RedirectResponse("/organizer/sign-in", status_code=status.HTTP_303_SEE_OTHER)
        
    # 5. AUTHENTIFICATION & REDIRECTION SÉCURISÉE 🎉
    # 💡 Sécurité : On nettoie les résidus du formulaire avant d'injecter la session finale
    request.session.clear()
    
    # 💡 Correctif Majeur : On utilise le gestionnaire de session natif (au lieu d'un cookie manuel en clair)
    request.session["session_user_id"] = user.id
    
    response = RedirectResponse(url="/organizer/account", status_code=status.HTTP_303_SEE_OTHER)
    return response

@Root.get("/organizer/auth/logout")
async def logout(request: Request):
    # 1. SÉCURITÉ : On nettoie la session utilisateur EN PREMIER.
    # Cela détruit instantanément 'session_user_id' et les restes de l'ancienne session.
    request.session.clear()
    
    # 💡 2. NETTOYAGE RÉSIDUEL : Si jamais tu utilises encore le cookie CSRF
    # Il est sain de le supprimer aussi au logout pour repartir sur une base neuve au prochain login.
    response = RedirectResponse(url="/organizer/sign-in", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="fastapi-csrf-token", path="/")
    
    return response