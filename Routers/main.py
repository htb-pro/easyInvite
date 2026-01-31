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


Root = APIRouter()

templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates
Root.mount("/static",StaticFiles(directory="static"), name="static")#ou sont stocker les fichier static

@Root.get("/",name="main_page",response_class=HTMLResponse)#get the main page
def get_main(request:Request):
    return templates.TemplateResponse("easyInviteApk/homePage/main.html",{'request':request})

#-----------------------about invitation view
@Root.get('/get_invite',name="invitation",response_class=HTMLResponse)#get the invite url
def getInvite(request:Request):
    return templates.TemplateResponse("Invitation/List/list.html",{'request':request})

@Root.get("/easyInvite",name="intro_link",response_class=HTMLResponse)#get the intro view
def intro_view(request:Request):
    return templates.TemplateResponse("easyInviteApk/Intro/intro.html",{'request':request})

