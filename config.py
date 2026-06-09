from fastapi import Request,HTTPException
from dotenv import load_dotenv
import os,hmac
from arq.connections import RedisSettings

load_dotenv()

secret = os.getenv('SECRET')#le secret ou sinature du token
algo = os.getenv('ALGO')#type d'algorithme
africa_talking_key = os.getenv('africa_talking_key')#at key
token_expire_minute = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTE',60))#duree d'expiration du token

# Remplace ton dictionnaire actuel par ceci :
redis_url = os.getenv("REDIS_URL")
REDIS_SETTINGS = RedisSettings.from_dsn(redis_url)
csrf_key = os.getenv('CSRF_SECRET')
    
def verify_csrf(request: Request):#methode de la verfication du token
    print("----------------------DEBUG: La fonction verify_csrf est appelée -----------------!")
    csrf_cookie = request.cookies.get("csrf_token")
    form_data = request._form # Récupère les données de formulaire déjà parsées
    csrf_form = form_data.get("csrf_token")
    print(f"--------------------------------{csrf_form}")
    try:
        if not csrf_cookie or not csrf_form:
            raise HTTPException(
                status_code=403,
                detail="CSRF token manquant"
            )

            # 3. Comparaison sécurisée (temps constant)
        if not hmac.compare_digest(csrf_cookie, csrf_form):
            raise HTTPException(status_code=403, detail="CSRF token invalide")
    except Exception as e:
        print(f"-----------------------------------{e}")