from fastapi import Request,HTTPException,FastAPI,status
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
import os,hmac
from arq.connections import RedisSettings
from contextlib import asynccontextmanager
from arq import create_pool
from sqlalchemy.future import select
from models import ExternalUser

load_dotenv()

set_secure_cookie = False #la variable permettant l'usage du csrf_token Fasle en locale et True en ligne ou prod#

secret = os.getenv('SECRET')#le secret ou sinature du token
algo = os.getenv('ALGO')#type d'algorithme
africa_talking_key = os.getenv('africa_talking_key')#at key
token_expire_minute = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTE',60))#duree d'expiration du token

#====================whatsapp
whatsap_phone_Number_ID = os.getenv('Phone_Number_ID')

whatsapp_token = os.getenv('whatsapp_token')

#=======================
account_sid = os.getenv('twilio_account_sid')
auth_token = os.getenv('twilio_auth_token')
twilio_number = os.getenv('twilio_whatsapp_number')
text_content= os.getenv('text_content_sid')
media_content = os.getenv('media_content_sid')
#=======================

# Remplace ton dictionnaire actuel par ceci :
redis_url = os.getenv("REDIS_URL")
REDIS_SETTINGS = RedisSettings.from_dsn(redis_url)
csrf_key = os.getenv('CSRF_SECRET')

arq_pool = None
@asynccontextmanager
async def lifespan(app: FastAPI):
    global arq_pool
    # 2. Au démarrage de FastAPI, on connecte le pool ARQ à Redis
    arq_pool = create_pool(REDIS_SETTINGS)
    print("🚀 Le pool ARQ est connecté à Redis et prêt à envoyer des tâches !")
    
    yield
    
    # 3. À la fermeture de l'application, on ferme proprement la connexion
    await arq_pool.close()
    print("🛑 Connexion au pool ARQ fermée.")

import hmac

async def verify_csrf(request: Request):
    # 1. Récupération du token stocké dans le cookie du navigateur
    cookie_token = request.cookies.get("fastapi-csrf-token")
    
    # 2. Récupération du token soumis via le formulaire
    form_data = await request.form()
    form_token = form_data.get("csrf_token")
    
    # --- LOGS DE DEBUGGING EN TERMINAL ---
    #print("======== DEBUG CSRF ========")
    #print(f"Token du Cookie     : {cookie_token}")
    #print(f"Token du Formulaire : {form_token}")
    #print("============================")
    
    # 3. Vérifications strictes
    if not cookie_token or not form_token:
        print("DEBUG: [403] Un des tokens est manquant !")
        raise HTTPException(status_code=403, detail="Sécurité CSRF : Données manquantes.")
        
    # 4. Comparaison sécurisée
    if not hmac.compare_digest(cookie_token, form_token):
        print("DEBUG: [403] Les tokens ne correspondent pas !")
        raise HTTPException(status_code=403, detail="Sécurité CSRF : Jeton invalide ou expiré.")
        
    # Si tout est OK, on laisse passer la requête
    return True
