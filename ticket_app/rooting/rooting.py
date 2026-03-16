from fastapi import APIRouter,Request
from fastapi.templating import Jinja2Templates
Root = APIRouter()
templates = Jinja2Templates(directory="Templates")
@Root.get("/paiements")
async def get_paiement_view(request:Request):
    return templates.TemplateResponse("ticket/index.html",{'request':request})