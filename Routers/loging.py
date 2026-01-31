#APIRouter permet juste l'organisation du code au lieu d' avoir tout les routes dans un fichier main oon cree les root separement
from fastapi import Request,Form,Depends,HTTPException,APIRouter
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uuid import uuid4
import models
from db_setting import engine,connecting
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models import *
from datetime import date
from typing import Optional
from datetime import datetime,date

models.Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory = "Templates")
Root = APIRouter()

@Root.get("/login",name="auth",response_class=HTMLResponse)#get the auth view
def auth_view(request:Request):
    return templates.TemplateResponse("easyInviteApk/Authentification/auth.html",{'request':request})