#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import APIRouter,Request,HTTPException,Depends,Form,status
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from datetime import datetime,timedelta
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from models import User,Role
from db_setting import connecting
import os,secrets
from jose import JWTError,jwt,ExpiredSignatureError
from config import secret,algo,token_expire_minute,set_secure_cookie,verify_csrf
from schemas import User as user_schemas
from typing import Optional
from fastapi import Request, Depends, status
from fastapi.responses import RedirectResponse

templates = Jinja2Templates(directory ="Templates")
pwd_context = CryptContext(schemes=["argon2"],deprecated="auto")
Root = APIRouter()
#verifier le token de l'utilisateur

# exceptions.py
class LoginRequiredException(Exception):
    def __init__(self, next_url: str = "/"):
        self.next_url = next_url



async def get_current_user_from_cookie(
    request: Request, 
    db: AsyncSession = Depends(connecting)
) -> User:
    token = request.cookies.get("access_token")
    current_path = request.url.path

    # 1. Pas de token -> Exception de redirection
    if not token:
        raise LoginRequiredException(next_url=current_path)

    if token.startswith("Bearer "):
        token = token.split(" ")[1]

    # 2. Validation du Token
    try:
        payload = jwt.decode(token, secret, algorithms=[algo])
        user_id: Optional[str] = payload.get("user")
        
        if user_id is None:
            raise LoginRequiredException(next_url=current_path)

    except (ExpiredSignatureError, JWTError):
        # Capturé proprement ! Déclenche la redirection
        raise LoginRequiredException(next_url=current_path)

    # 3. Récupération en Base de données
    stmt = (
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    result = await db.execute(stmt)
    user = result.scalars().first()

    # 4. Compte introuvable ou inactif
    if not user or (hasattr(user, "is_active") and not user.is_active):
        raise LoginRequiredException(next_url=current_path)

    return user

#methode verifier le role pour acceder a une vue 
async def admin_required(user:user_schemas = Depends(get_current_user_from_cookie)):
    if not any(role.name == "admin" for role in user.roles):
        raise HTTPException(status_code = 403,detail="accès refusé")
    return user

#middleware pour la pretection des pages 
oauth_scheme =OAuth2PasswordBearer(tokenUrl = "login")
def get_curent_user(token:str = Depends(oauth_scheme)):
    user = verify_token(token)
    if not user :
        raise HTTPException(status_code = status.HTTP_401_UNAUTHORIZED,detail = "non autorisé")
    return user

def hash_password(password: str) -> str:
    """
    Méthode pour le hachage sécurisé du password.
    Limite à 72 caractères pour éviter le crash matériel de l'algorithme Bcrypt.
    """
    if not password:
        raise ValueError("Le mot de passe ne peut pas être vide.")
        
    # 🛡️ Sécurité & Stabilité : On tronque manuellement à 72 caractères maximum
    safe_password = password[:72]
    
    # On génère et on retourne le hash Bcrypt standard (qui fera toujours 60 caractères)
    return pwd_context.hash(safe_password)

def verify_password(password: str, hashed: str) -> bool:
    # 1. Protection contre les valeurs vides ou None
    if not password or not hashed:
        return False

    try:
        # 2. 🛡️ Sécurité Bcrypt : Tronquer strictement à 72 OCTETS (bytes)
        # On encode en UTF-8, on découpe les 72 premiers octets, puis on décode
        safe_password_bytes = password.encode('utf-8')[:72]
        safe_password = safe_password_bytes.decode('utf-8', errors='ignore')

        # 3. Vérification classique
        return pwd_context.verify(safe_password, hashed)

    except ValueError as e:
        # Si le mot de passe en BDD est mal formé ou le hash corrompu
        print(f"⚠️ [BDD] Le hash en base de données est invalide ou corrompu : {hashed}. Erreur : {e}")
        return False
    except Exception as e:
        # Capture tout autre imprévu sans faire crasher la route
        print(f"⚠️ [AUTH] Erreur inattendue lors de la vérification : {e}")
        return False

def create_token(data:dict):#Creation du token
    data_to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=token_expire_minute)
    data_to_encode.update({"exp":expire})
    return jwt.encode(data_to_encode,secret,algorithm = algo)

def verify_token(token:str):#verification du token
    try:
        payload = jwt.decode(token,secret,algorithms = [algo])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code = 401,detail = "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code = 401,detail = "token invalide")

@Root.get("/get/auth",name="intro_link")#get the intro view
def intro_view(request:Request):
    return templates.TemplateResponse("Authentification/forms/home.html",{'request':request})


@Root.get("/logout",name="logout")#get the auth view
def logout():
    response = RedirectResponse("/login",status_code = 302)
    response.delete_cookie("access_token",path = "/")
    return response

@Root.get("/login",name="auth")#get the auth view
def auth_view(request:Request):
    csrf_token = secrets.token_urlsafe(32)
    response = templates.TemplateResponse("Authentification/forms/auth.html",{'request':request,'csrf_token':csrf_token})
    response.set_cookie(
    key="fastapi-csrf-token",
    value=csrf_token,
    httponly=set_secure_cookie,   # 🔒 Empêche les attaques XSS (JavaScript ne peut pas lire le cookie)
    secure=set_secure_cookie,     # 🔒 Exige HTTPS (obligatoire en prod)
    samesite="lax",  # 🔒 Protection contre les attaques CSRF
)
    return response

@Root.post("/login")
async def login(
    request: Request,
    csrf_token: str = Form(...),
    bobby_pot: str = Form(None),  # Honeypot anti-bot
    next: str = Form(None),       # 👈 Récupère la destination après connexion
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(connecting),
    _=Depends(verify_csrf)
):
    # 1. Détection du Honeypot (Anti-bot)
    if bobby_pot:
        # On simule un échec sans révéler qu'il s'agit d'un piège
        return templates.TemplateResponse(
            "Authentification/forms/auth.html",
            {"request": request, "message": "Nom d'utilisateur ou mot de passe incorrect"}
        )
    
    # 2. Recherche de l'utilisateur
    user_email = form_data.username.strip() # Nettoyage de l'email
    user_res = await db.execute(select(User).where(User.email == user_email))
    user = user_res.scalars().first()

    # 3. Vérification de l'existence ET du mot de passe (Sécurité anti-timing attack)
    # ⚠️ On vérifie `if not user` SANS toucher à `user.id` avant !
    if not user or not verify_password(form_data.password, user.password):
        return templates.TemplateResponse(
            "Authentification/forms/auth.html",
            {"request": request, "message": "Nom d'utilisateur ou mot de passe incorrect",'csrf_token':csrf_token}
        )

    # 4. Vérification de l'état du compte
    if user.state != "active":
        return templates.TemplateResponse(
            "Authentification/forms/auth.html",
            {"request": request, "message": "Compte bloqué ou inactif.",'csrf_token':csrf_token}
        )
    
    # 6. Création du Token et Réponse
    access_token = create_token(data={"user": user.id})
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    # 7. Cookie de Session Sécurisé pour la Production
    response.set_cookie(
        key="access_token",
        value=access_token,       # Si ton middleware attend "Bearer ...", mets f"Bearer {access_token}"
        httponly=True,            # Anti-XSS
        secure=True,              # Exige HTTPS (Production)
        samesite="lax",           # Anti-CSRF
        max_age=86400 * 7         # Expiration (ex: 7 jours en secondes)
    )

    return response


