from fastapi import APIRouter,Request
from fastapi.templating import Jinja2Templates
Root = APIRouter()
templates = Jinja2Templates(directory="Templates")
