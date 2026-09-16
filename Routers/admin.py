import secrets
from typing import Optional
from uuid import UUID
from fastapi import Request,APIRouter,Form,Depends,HTTPException,status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from models import Group,Role,Permission,Event,Guest,Order
from sqlalchemy import select,func,delete
from sqlalchemy.orm import selectinload
from db_setting import connecting,AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import Group as group_schemas
from Routers.loging import get_current_user_from_cookie,admin_required
from config import set_secure_cookie as set,verify_csrf
from app.security.permissions import permission_required
import os,shutil,qrcode,io
from fastapi.responses import StreamingResponse

Root = APIRouter(tags = ["easyInvite"],dependencies =[Depends(get_current_user_from_cookie),Depends(admin_required)])
templates= Jinja2Templates(directory="Templates")

@Root.get("/admin_dashboard",name="adm_dashboard")
async def get_admin_dashboard(request:Request,db:AsyncSession = Depends(connecting)):
    group_id = request.query_params.get("group_id")
    async with AsyncSessionLocal() as session:
        event_count = await session.execute(select(func.count()).select_from(Event))#Nombre des  items enregistrer
        actif_event_count = await session.execute(select(func.count()).select_from(Event).where(Event.state == "en cours"))#Nombre des  items enregistrer
        pending_event_count = await session.execute(select(func.count()).select_from(Event).where(Event.state == "en attente"))#Nombre des  items enregistrer
        guest_count = await session.execute(select(func.count()).select_from(Guest))#Nombre des  items enregistrer
        total_event = event_count.scalar()
        total_guest = guest_count.scalar()
        total_actif_event = actif_event_count.scalar()
        total_pending_event = pending_event_count.scalar()
    query = select(Event).options(selectinload(Event.guests))
    if group_id:
        query = query.where(Event.group_id == group_id).options(selectinload(Event.guests))
    get_event_res = await db.execute(query)
    events = get_event_res.scalars().all()
    group_res= await db.execute(select(Group))
    groups = group_res.scalars().all()
    return templates.TemplateResponse("Authentification/admin/admin_dashboard.html",{'request':request,'groups':groups,'events':events,'total_event':total_event,'total_guest':total_guest,'total_actif_event':total_actif_event,'total_pending_event':total_pending_event})

@Root.get("/see_event/{event_id}")
async def get_detail_event(request:Request,event_id :str,db:AsyncSession = Depends(connecting)):
    event_res = await db.execute(select(Event).where(Event.id == event_id).options(selectinload(Event.guests),selectinload(Event.groups)))
    event = event_res.scalars().first()
    return templates.TemplateResponse("Authentification/admin/event/detail_event.html",{'request':request,'event':event})

@Root.get("/admin_list_event",name = "adm_list_event")
async def get_event_list(request:Request,db:AsyncSession = Depends(connecting)):
    event_name =request.query_params.get('event_name')
    query = select(Event).options(selectinload(Event.groups),selectinload(Event.guests))
    if event_name:
        query = query.where(Event.name == event_name)
    event_res = await db.execute(query)
    events = event_res.scalars().all()
    success_delation = request.session.pop('orders_deleted_message',None)
    not_found = request.session.pop('orders_not_found_message',None)
    return templates.TemplateResponse("Authentification/admin/event/list.html",{'request':request,'not_found_message':not_found,'delation_message':success_delation,'events':events})

@Root.get("/settings/roles-permissions",name="access_manager")
async def show_settings_page(request: Request,success: Optional[str] = None, db: AsyncSession = Depends(connecting)):
    # Récupération indépendante de chaque liste
    roles = (await db.scalars(select(Role))).all()
    permissions = (await db.scalars(select(Permission))).all()
    groups = (await db.scalars(select(Group))).all()
    existing_message = request.session.pop('group_existing_message', None) or \
                       request.session.pop('role_existing_message', None) or \
                       request.session.pop('perms_existing_message', None)
    if existing_message:
        existing_message = existing_message.strip()
    csrf_token = secrets.token_urlsafe(32)
    response= templates.TemplateResponse(
        "Authentification/admin/list/list_role_perms_group.html",
        {
            "request": request,
            "roles": roles,
            "permissions": permissions,
            "groups": groups,
            "success": success,
            "failled": existing_message,
            "csrf_token": csrf_token
        }
    )
    response.set_cookie(key="fastapi-csrf-token", 
                        value=csrf_token, 
                        httponly=set,
                        samesite="lax",
                        secure=set)
    return response

@Root.post("/create_group")#la creation d'un groupe
async def create_group(request:Request,group_name: str = Form(...),csrf_token: str = Form(...),db:AsyncSession = Depends(connecting),_=Depends(verify_csrf)):
    group_res =await  db.execute(select(Group).where(Group.name==group_name))
    group = group_res.scalars().first()
    message = None
    if group:
        message = "un group exist avec ce nom "
        request.session['group_existing_message'] = message
        return RedirectResponse("/settings/roles-permissions",303)
    new_group = Group(
        name = group_name
    )
    db.add(new_group)
    await db.commit()
    await db.refresh(new_group)
    return RedirectResponse("/settings/roles-permissions",303)

@Root.post("/groups/{group_id}/update")
async def update_group(
    group_id: str,
    name: str = Form(...),
    db: AsyncSession = Depends(connecting)
):
    # Recherche du groupe à modifier
    result = await db.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé"
        )

    # Mise à jour du nom
    group.name =name.strip()

    try:
        await db.commit()
        await db.refresh(group)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erreur lors de la modification du groupe (nom probablement déjà existant)."
        )

    return RedirectResponse(
        url="/settings/roles-permissions?success=Groupe+modifi%C3%A9+avec+succ%C3%A8s",
        status_code=status.HTTP_303_SEE_OTHER
    )


# 2. SUPPRESSION D'UN GROUPE
@Root.post("/groups/{group_id}/delete")
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(connecting)
):
    # Recherche du groupe à supprimer
    result = await db.execute(
        select(Group).where(Group.id == group_id)
    )
    group = result.scalars().first()

    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Groupe non trouvé"
        )

    # Suppression du groupe
    try:
        await db.delete(group)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer ce groupe (il contient peut-être des utilisateurs associés)."
        )

    return RedirectResponse(
        url="/settings/roles-permissions?success=Groupe+supprim%C3%A9+avec+succ%C3%A8s",
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.post("/create_role")#la creation d'un role
async def create_role(request:Request,role_name: str = Form(...),csrf_token: str = Form(...),db:AsyncSession = Depends(connecting),_=Depends(verify_csrf)):
    role_res =await  db.execute(select(Role).where(Role.name==role_name))
    role = role_res.scalars().first()
    message = None
    if role:
        message = "un group exist avec ce nom "
        request.session['role_existing_message'] = message
        return RedirectResponse("/settings/roles-permissions",303)
    new_role = Role(
        name = role_name
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)
    return RedirectResponse("/settings/roles-permissions",303)

@Root.post("/roles/{role_id}/update")
async def update_role(
    role_id: str,
    name: str = Form(...),
    db: AsyncSession = Depends(connecting)
):
    # 1. Recherche du rôle existant
    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalars().first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé"
        )

    # 2. Mise à jour des champs et sauvegarde
    try:
        role.name = name.strip()
        await db.commit()
        await db.refresh(role)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erreur lors de la mise à jour (nom peut-être déjà existant)."
        )

    # 3. Redirection vers la page d'administration
    return RedirectResponse(
        url="/settings/roles-permissions?success=R%C3%B4le+modifi%C3%A9+avec+succ%C3%A8s",
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.post("/roles/{role_id}/delete")
async def delete_role(
    role_id: str,
    db: AsyncSession = Depends(connecting)
):
    # 1. Recherche du rôle existant
    result = await db.execute(
        select(Role).where(Role.id == role_id)
    )
    role = result.scalars().first()

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rôle non trouvé"
        )

    # 2. Suppression et validation de la transaction
    try:
        await db.delete(role)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Impossible de supprimer ce rôle (il est probablement attribué à un ou plusieurs utilisateurs)."
        )

    # 3. Redirection vers la page d'administration
    return RedirectResponse(
        url="/settings/roles-permissions?success=R%C3%B4le+supprim%C3%A9+avec+succ%C3%A8s",
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.post("/create_permission")#la creation d'un role
async def create_group(request:Request,permission_name: str = Form(...),csrf_token: str = Form(...),db:AsyncSession = Depends(connecting),_=Depends(verify_csrf)):
    perm_res =await  db.execute(select(Permission).where(Permission.name==permission_name))
    permission = perm_res.scalars().first()
    message = None
    if permission:
        message ="cette permission exist deja "
        request.session['perms_existing_message'] = message
        return RedirectResponse("/settings/roles-permissions",303)
    new_perm = Permission(
        name = permission_name
    )
    db.add(new_perm)
    await db.commit()
    await db.refresh(new_perm)
    return RedirectResponse("/settings/roles-permissions",303)

@Root.post("/permissions/{permission_id}/update")
async def update_permission(
    permission_id: str,
    name: str = Form(...),
    db: AsyncSession = Depends(connecting)
):
    # 1. Recherche de la permission en base
    result = await db.execute(
        select(Permission).where(Permission.id == permission_id)
    )
    permission = result.scalars().first()

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée"
        )

    # 2. Mise à jour des champs
    permission.name = name.strip()

    # 3. Validation et enregistrement
    try:
        await db.commit()
        await db.refresh(permission)
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erreur lors de la mise à jour (nom peut-être déjà existant)."
        )

    # 4. Redirection vers la page d'administration
    return RedirectResponse(
        url="/settings/roles-permissions?success=Permission+mise+%C3%A0+jour",
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.post("/permissions/{permission_id}/delete")
async def delete_permission(
    permission_id: str,
    db: AsyncSession = Depends(connecting)
):
    # 1. Recherche de la permission en base
    result = await db.execute(
        select(Permission).where(Permission.id == permission_id)
    )
    permission = result.scalars().first()

    if not permission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permission non trouvée"
        )

    # 2. Suppression de l'élément
    try:
        await db.delete(permission)
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Erreur lors de la suppression (cette permission est peut-être rattachée à un rôle)."
        )

    # 3. Redirection vers la page d'administration
    return RedirectResponse(
        url="/settings/roles-permissions?success=Permission+supprim%C3%A9e",
        status_code=status.HTTP_303_SEE_OTHER
    )

@Root.get("/permission_assigning/form",name="assign")
async def assign_form(request:Request,db:AsyncSession = Depends(connecting)):
    roles_res = await db.execute(select(Role))
    roles = roles_res.scalars().all()
    perms_res = await db.execute(select(Permission))
    permissions = perms_res.scalars().all()
    return templates.TemplateResponse("Authentification/forms/assign_permission.html",{'request':request,'roles':roles,'permissions':permissions})

@Root.post("/assign-permissions")
async def get_roles_permissions(request:Request,role_id:str = Form([]),permission_ids:list[str] = Form([]),db:AsyncSession = Depends(connecting)):
    role_res = await db.execute(select(Role).where(Role.id ==role_id).options(selectinload(Role.permissions)))
    role = role_res.scalars().first()
    if role :
        selected_permissions_res= await db.execute(select(Permission).where(Permission.id.in_(permission_ids)))
        selected_permissions = selected_permissions_res.scalars().all()
        role.permissions = selected_permissions
        await db.commit()
    return RedirectResponse(url="/permission_assigning/form",status_code = 303)

@Root.get("/params",name="params")
async def get_params_view(request:Request):
    return templates.TemplateResponse("Authentification/admin/setting_admin_option.html",{'request':request})

@Root.post("/admin/delete_event/{event_id}")
async def deleteEvent(request:Request,event_id:str,db:AsyncSession = Depends(connecting),user = Depends(permission_required("delete_event"))):
    event_to_delete =select(Event).where(Event.id==event_id)
    res = await db.execute(event_to_delete)
    eventToDelete = res.scalars().first()
    if not eventToDelete:
        raise HTTPException(status_code=404,detail="cette evenement n'existe pas")
    Pictures= f"static/Pictures/{event_id}"#dossier de l'image de l'evenement
    is_dir_exist = os.path.exists(Pictures)#exist il ?
    if is_dir_exist: #si oui 
        shutil.rmtree(Pictures)#qu'il soit supprimer
    await db.delete(eventToDelete)
    await db.commit()
    return RedirectResponse("/admin_dashboard",status_code=303)

@Root.get("/delete_all_order/{event_id}")
async def delete_orders(request: Request, event_id: str, db: AsyncSession = Depends(connecting),user = Depends(permission_required("delete_order"))):
    # 1. Utilisation de l'instruction DELETE native de SQLAlchemy (plus rapide)
    stmt = delete(Order).where(Order.event_id == event_id)
    result = await db.execute(stmt)
    
    # 2. Vérification si quelque chose a été supprimé
    if result.rowcount == 0:
        request.session['orders_not_found_message']="Aucune commande trouvée pour cet événement"
        return RedirectResponse("/admin_list_event", status_code=303)
    try:
    # 3. Validation
        await db.commit()
    except:
        await db.rollback()
        raise HTTPException(status_code=500,detail="erreur lors de la supressions")
    request.session['orders_deleted_message'] = "toutes les commandes on ete supprimer avec succé"
    return RedirectResponse("/admin_list_event", status_code=303)

@Root.get("/delete_all_guests/{event_id}")
async def delete_guests(request: Request, event_id: str, db: AsyncSession = Depends(connecting),user = Depends(permission_required("delete_guest"))):
    # 1. Utilisation de l'instruction DELETE native de SQLAlchemy (plus rapide)
    stmt = delete(Guest).where(Guest.event_id == event_id)
    result = await db.execute(stmt)
    
    # 2. Vérification si quelque chose a été supprimé
    if result.rowcount == 0:
        request.session['orders_not_found_message']="Aucun evenment trouvée "
        return RedirectResponse("/admin_list_event", status_code=303)
    try:
    # 3. Validation
        await db.commit()
    except:
        await db.rollback()
        raise HTTPException(status_code=500,detail="erreur lors de la supressions")
    request.session['orders_deleted_message'] = "tous les invites on ete supprimer avec succé"
    return RedirectResponse("/admin_list_event", status_code=303)

@Root.get("/qr-whatsapp-ui")
async def page_test_qr(request: Request):
    csrf_token = secrets.token_urlsafe(32)
    response =  templates.TemplateResponse(
        "Authentification/admin/event/forms/qr_generating_form.html",
        {
            "request": request,
            "csrf_token": csrf_token
        }
    )
    response.set_cookie(key="fastapi-csrf-token", 
                        value=csrf_token, 
                        httponly=set,
                        samesite="lax",
                        secure=set)
    return response
# 2. ROUTE POST : Reçoit la donnée et télécharge le fichier PNG du QR Code
@Root.post("/telecharger-qrcode")
async def telecharger_qrcode(
    request: Request,
    qr_data: str = Form(...),
    csrf_token: str = Form(...),
    _ = Depends(verify_csrf)
):
    # 1. Validation de la donnée
    qr_data_clean = qr_data.strip()
    if not qr_data_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La donnée du QR Code (qr_data) ne peut pas être vide."
        )
    
    # Limite de sécurité sur la taille pour éviter les attaques DoS mémoire
    if len(qr_data_clean) > 2048:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La longueur du texte dépasse la limite autorisée (2048 caractères)."
        )

    try:
        # 2. Génération du QR Code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data_clean)
        qr.make(fit=True)

        # 3. Création du flux d'image PNG en mémoire
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        # 4. Envoi du fichier
        filename = "qrcode_du_groupe.png"
        return StreamingResponse(
            buffer,
            media_type="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erreur lors de la génération du QR Code : {str(e)}"
        )