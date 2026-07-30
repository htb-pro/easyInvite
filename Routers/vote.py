from fastapi import APIRouter, Depends, HTTPException, status,Request,Form,File, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi.templating import Jinja2Templates
from models import Event,Vote,Candidate
from config import check_current_user_session,Cloud_name,Cloud_api_key,Cloud_api_secret
from db_setting import connecting
import os,shutil,cloudinary,cloudinary.uploader,asyncio
from uuid import uuid4
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

Root=APIRouter()
templates = Jinja2Templates(directory="Templates")


cloudinary.config(
    cloud_name = Cloud_name,
    api_key = Cloud_api_key,    
    api_secret  = Cloud_api_secret,
    secure = True
)





@Root.post("/api/events/{event_id}/vote/{candidate_id}")
async def submit_free_vote(
    request: Request,
    event_id: str,
    candidate_id: str,
    current_user: str = Depends(check_current_user_session),
    db: AsyncSession = Depends(connecting)
):
    user_id = current_user

    try:
        # 1. Vérifier si l'utilisateur a DÉJÀ voté
        stmt = select(Vote).where(
            Vote.user_id == user_id, 
            Vote.event_id == event_id
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vous avez déjà exprimé votre vote pour ce concours !"
            )

        # 2. Vérifier si le candidat existe pour cet événement
        cand_stmt = select(Candidate).where(
            Candidate.id == candidate_id, 
            Candidate.event_id == event_id
        )
        cand_result = await db.execute(cand_stmt)
        candidate = cand_result.scalars().first()

        if not candidate:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Candidat introuvable pour cet événement"
            )

        # 3. Enregistrer le vote
        new_vote = Vote(
            user_id=user_id,
            candidate_id=candidate_id,
            event_id=event_id
        )
        db.add(new_vote)
        
        # 4. Incrémentation directe sur l'instance Python
        candidate.votes_count = (candidate.votes_count or 0) + 1
        
        # 5. Validation de la transaction
        await db.commit()
        await db.refresh(candidate) # 👈 Fonctionne parfaitement maintenant

        return {
            "status": "success", 
            "message": "Vote enregistré avec succès !",
            "new_votes_count": candidate.votes_count
        }

    except HTTPException:
        raise

    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous avez déjà exprimé votre vote pour ce concours !"
        )

    except Exception as e:
        await db.rollback()
        print(f"🚨 [PROD VOTE ERROR] : {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Une erreur technique est survenue."
        )
    
@Root.get("/events/{event_id}/candidates/add")
async def get_add_candidate_form(request: Request, event_id: str, db: AsyncSession = Depends(connecting)):
     # 1. Requête pour récupérer l'événement avec ses candidats et ses billets
    query = (
        select(Event)
        .where(Event.id == event_id)
    )
    result = await db.execute(query)
    event = result.scalar_one_or_none()
    form_data_session = request.session.pop("form_data",None)
    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    if form_data_session is None:
        form_data = {
            "errors":{
                "name":"",
                "candidate_number":"",
                "photo":"",
            },
            "fields": {
                "name": "",             # <-- Initialisé pour éviter l'erreur de clé absente
                "candidate_number": ""  # <-- Initialisé
            }
        }
    else :
        form_data = form_data_session
    
    return templates.TemplateResponse("/e-ticket/vote/forms/candidate/candidate.html", {
        "request": request,
        "event": event,
        "data":form_data # Mode Création
    })

# 2. POST - Traiter la soumission du formulaire
@Root.post("/events/{event_id}/candidates/add") #done
async def create_candidate(
    request: Request,
    event_id: str,
    name: str = Form(...),
    candidate_number: str = Form(...),
    bio: str = Form(None),
    photo: UploadFile = File(None),
    db: AsyncSession = Depends(connecting)
):
    # 1. Vérification de l'existence de l'événement
    query_event = select(Event).where(Event.id == event_id)
    result_event = await db.execute(query_event)
    event = result_event.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    # 2. Vérification d'unicité du numéro
    cand_query = select(Candidate).where(
        Candidate.candidate_number == candidate_number.strip(),
        Candidate.event_id == event_id
    )
    result_cand = await db.execute(cand_query)
    candidate_exist = result_cand.scalar_one_or_none()

    # 3. Validation des données du formulaire
    name_error = ""
    if len(name.strip()) < 2:
        name_error = "Le nom doit contenir au moins 2 caractères."

    number_error = ""
    if candidate_exist:
        number_error = "Un(e) candidat(e) existe déjà avec ce numéro pour cet événement."

    form_data = {
        "errors": {
            "name": name_error,
            "candidate_number": number_error,
            "photo": ""
        },
        "fields": {
            "name": name,
            "candidate_number": candidate_number,
            "bio": bio,
        }
    }

    # 4. Traitement du fichier photo (Non-bloquant / Asynchrone)
    photo_url = None
    photo_public_id = None

    if photo and photo.filename and photo.filename.strip():
        try:
            # S'assurer qu'on lit le fichier depuis le début
            await photo.seek(0)

            # Execution de l'upload Cloudinary dans un thread séparé (évite de bloquer l'Event Loop)
            upload_result = await asyncio.to_thread(
                cloudinary.uploader.upload,
                photo.file,
                folder="EasyTicket/Candidates",
                resource_type="image"
            )
            
            photo_url = upload_result.get("secure_url")
            photo_public_id = upload_result.get("public_id")

        except Exception as e:
            print(f"🚨 Erreur Cloudinary Prod : {str(e)}")
            form_data["errors"]["photo"] = "Impossible d'envoyer la photo. veillez vous connecter a internet ou  réessayez."
        finally:
            # Libération du fichier en mémoire
            await photo.close()

    # 5. Redirection en cas d'erreur de formulaire
    if any(form_data["errors"].values()):
        request.session["form_data"] = form_data
        return RedirectResponse(
            url=f"/events/{event_id}/candidates/add", 
            status_code=status.HTTP_303_SEE_OTHER
        )

    # 6. Transaction BDD Sécurisée
    try:
        new_candidate = Candidate(
            event_id=event_id,
            name=name.strip(),
            candidate_number=candidate_number.strip(),
            photo_url=photo_url,
            photo_public_id=photo_public_id,
            bio=bio.strip() if bio else None,
            votes_count=0
        )

        db.add(new_candidate)
        await db.commit()

    except Exception as e:
        await db.rollback()
        print(f"🚨 Erreur BDD Prod : {str(e)}")
        
        # Rollback distant Cloudinary pour éviter les fichiers orphelins
        if photo_public_id:
            try:
                await asyncio.to_thread(cloudinary.uploader.destroy, photo_public_id)
            except Exception:
                pass

        raise HTTPException(
            status_code=500, 
            detail="Une erreur interne est survenue lors de la création du candidat."
        )

    request.session["success_message"] = "Candidat ajouté avec succès !"
    return RedirectResponse(
        url=f"/events/{event_id}/candidates/add", 
        status_code=status.HTTP_303_SEE_OTHER
    )