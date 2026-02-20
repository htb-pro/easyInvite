#importation-
from fastapi import FastAPI
from Routers.event import Root
from Routers.guest import Root as guest_root
from Routers.invite import Root as invite_root
from Routers.main import Root as main_root
from Routers.chekin import Root as checkin_root
from Routers.loging import Root as log_root
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from db_setting import init_db

#initialisation
Apk = FastAPI()

@Apk.on_event("startup")
async def on_startup():
    await init_db()
Apk.add_middleware(SessionMiddleware,secret_key = "super-secret-key-123")
Apk.mount("/static",StaticFiles(directory="static"),name="static")
Apk.include_router(Root)
Apk.include_router(guest_root)
Apk.include_router(invite_root)
Apk.include_router(main_root)
Apk.include_router(checkin_root)
Apk.include_router(log_root)


