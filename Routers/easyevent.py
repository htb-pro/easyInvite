# from fastapi import Request,Depends,APIRouter
# from fastapi.templating import Jinja2Templates
# from datetime import datetime

# Root = APIRouter()
# templates = Jinja2Templates(directory="Templates")#ou sont stocker les templates

# @Root.get('/')#get the invite url
# def getInvite(request:Request):
#     copyright = datetime.now().year
#     return templates.TemplateResponse("easyevent/index.html",{'request':request,'copyright': copyright})

# @Root.get('/easyinvite')#get the invite url
# def getInvite(request:Request):
#     copyright = datetime.now().year
#     return templates.TemplateResponse("easyevent/e_invite_site/index.html",{'request':request,'copyright': copyright})

# @Root.get('/easyevent/ecosys')#get the invite url
# def getInvite(request:Request):
#     copyright = datetime.now().year
#     return templates.TemplateResponse("easyevent/ecosystem.html",{'request':request,'copyright': copyright})

# @Root.get('/easyinvite/getintouch')#get the invite url
# def getInvite(request:Request):
#     copyright = datetime.now().year
#     return templates.TemplateResponse("easyevent/e_invite_site/forms/getInTouchForm.html",{'request':request,'copyright': copyright})

# @Root.get('/easyinvite/tarif')#get the invite url
# def getInvite(request:Request):
#     copyright = datetime.now().year
#     return templates.TemplateResponse("easyevent/e_invite_site/tarification.html",{'request':request,'copyright': copyright})