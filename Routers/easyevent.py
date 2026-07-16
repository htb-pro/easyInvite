import secrets
from fastapi import Request,Depends,APIRouter,Form
from fastapi.templating import Jinja2Templates
from datetime import datetime
from config import set_secure_cookie,verify_csrf

Root = APIRouter()
templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates



# @Root.get('/easyinvite')#get the invite url
# def getInvite(request:Request):
#     copyright = datetime.now().year
#     return templates.TemplateResponse("easyevent/e_invite_site/index.html",{'request':request,'copyright': copyright})

@Root.get('/easyevent')#get the invite url
def getInvite(request:Request):
    copyright = datetime.now().year
    csrf_token = secrets.token_urlsafe(32)  # Generate a random CSRF token
    response =  templates.TemplateResponse("easyevent/index.html",{'request':request,'copyright': copyright,'csrf_token': csrf_token})
    response.set_cookie(
        key="fastapi-csrf-token",
        value=csrf_token,
        httponly=True,
        secure=set_secure_cookie,
        samesite="lax",
    )
    return response

@Root.post("/easyevent/submit_form")
async def submit_event_request_form(request:Request,csrf_token:str = Form(...),event_type:str = Form(...),guest_count:str = Form(...),services:str = Form(...),
    event_city:str = Form(...),organizer_name:str = Form(...),organizer_phone:str = Form(...)):
    print("Received form data:", {
        "event_type": event_type,
        "guest_count": guest_count,
        "services": services,
        "event_city": event_city,
        "organizer_name": organizer_name,
        "organizer_phone": organizer_phone
    })
    pass


@Root.get('/data-management')
async def get_data_management(request:Request):
    copyright = datetime.now().year
    return templates.TemplateResponse("easyevent/management/dashboard/index.html",{'request':request,'copyright': copyright})