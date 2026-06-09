#importation-
from fastapi import FastAPI,status,HTTPException,Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from Routers.event import Root
from ticket_app.rooting.rooting import Root as ticket_root
from Routers.guest import Root as guest_root
from Routers.invite import Root as invite_root
from Routers.main import Root as main_root
from Routers.payment import Root as payment_root
from Routers.ticket import Root as ticket_root
from Routers.order import Root as order_root
from Routers.chekin import Root as checkin_root
from Routers.loging import Root as log_root
from Routers.user import Root as user_root
from Routers.admin import Root as admin_root
from Routers.event_dashboard import Root as event_dashboard_root
from Routers.external_user import Root as external_user_root
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from db_setting import init_db,AsyncSessionLocal
from config import secret
from app.init_admin import create_admin
#fastapi.middleware.cors import CORSMiddleware
from fastapi_csrf_protect import CsrfProtect
from pydantic import BaseModel

templates = Jinja2Templates(directory = "Templates")
#initialisation
Apk = FastAPI()
@Apk.on_event("startup")
async def on_startup():
    await init_db()
    async with AsyncSessionLocal() as db:
        await create_admin(db)

# CORS pour permettre frontend local
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

Apk.add_middleware(SessionMiddleware,secret_key = secret,https_only = True,same_site = "lax")
Apk.mount("/static",StaticFiles(directory="static"),name="static")
Apk.include_router(Root)
Apk.include_router(ticket_root)
Apk.include_router(guest_root)
Apk.include_router(invite_root)
Apk.include_router(main_root)
Apk.include_router(payment_root)
Apk.include_router(ticket_root)
Apk.include_router(order_root)
Apk.include_router(checkin_root)
Apk.include_router(log_root)
Apk.include_router(user_root)
Apk.include_router(admin_root)
Apk.include_router(event_dashboard_root)
Apk.include_router(external_user_root)

@Apk.exception_handler(HTTPException)
def auth_exception_handler(request,exc):
    if exc.status_code ==401:
        return RedirectResponse("/login",status_code = status.HTTP_302_FOUND)
    return str(exc.detail)

@Apk.exception_handler(403)#methode pour l'exception 403
async def forbidden_handler(request:Request,exc:HTTPException):
    return templates.TemplateResponse("Authentification/admin/admin_required_message.html",{'request':request,"message":exc.detail},status_code = 403)#le template qui sera renvoyer a chaque tantative d'un ayant pas droit a une vue ou donnees

#configuration de csrf_token
from config import csrf_key

app = FastAPI()

# Configuration
class CsrfSettings(BaseModel):
    secret_key: str = csrf_key
    csrf_cookie_key: str = "fastapi-csrf-token"
    csrf_cookie_secure: bool = False
    csrf_cookie_samesite: str = "lax"
    
    # C'est la configuration clé pour les formulaires HTML classiques
    csrf_token_key: str = "csrf_token" 
    csrf_header_name: str = "X-CSRF-TOKEN"
    
    # On indique explicitement d'utiliser le cookie pour valider
    csrf_in_cookies: bool = True
@CsrfProtect.load_config
def get_csrf_config():
    return CsrfSettings(
        csrf_token_key="csrf_token" 
    )
