#importation-
from fastapi import FastAPI,status,HTTPException,Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from Routers.event import Root
from Routers.guest import Root as guest_root
from Routers.invite import Root as invite_root
from Routers.main import Root as main_root
from Routers.chekin import Root as checkin_root
from Routers.loging import Root as log_root
from Routers.user import Root as user_root
from Routers.admin import Root as admin_root
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from db_setting import init_db,AsyncSessionLocal
from config import secret
from app.init_admin import create_admin
from recreation import recreate_tables

templates = Jinja2Templates(directory = "Templates")
#initialisation
Apk = FastAPI()
@Apk.on_event("startup")
async def on_startup():
    await init_db()
    #await recreate_tables()
    async with AsyncSessionLocal() as db:
        await create_admin(db)

Apk.add_middleware(SessionMiddleware,secret_key = secret,https_only = True,same_site = "lax")
Apk.mount("/static",StaticFiles(directory="static"),name="static")
Apk.include_router(Root)
Apk.include_router(guest_root)
Apk.include_router(invite_root)
Apk.include_router(main_root)
Apk.include_router(checkin_root)
Apk.include_router(log_root)
Apk.include_router(user_root)
Apk.include_router(admin_root)


@Apk.exception_handler(HTTPException)
def auth_exception_handler(request,exc):
    if exc.status_code ==401:
        return RedirectResponse("/login",status_code = status.HTTP_302_FOUND)
    return str(exc.detail)

@Apk.exception_handler(403)#methode pour l'exception 403
async def forbidden_handler(request:Request,exc:HTTPException):
    return templates.TemplateResponse("Authentification/admin/admin_required_message.html",{'request':request,"message":exc.detail},status_code = 403)#le template qui sera renvoyer a chaque tantative d'un ayant pas droit a une vue ou donnees
