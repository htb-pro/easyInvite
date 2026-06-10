import io
from sqlalchemy.future import select
from arq.connections import RedisSettings
# Importe tes configurations réelles
from utils.redis_config import redis_conn,REDIS_SETTINGS
from Routers.ticket import generate_order_pdf_in_memory,generate_ticket_pdf_in_memory# Ta fonction de dessin PDF
from models import Ticket,Order
from db_setting import AsyncSessionLocal
async def generate_pdf_task(ctx, order_id: str):#une tache que doit faire arq qui est de generer les billets
    """Tâche ARQ exécutée en arrière-plan pour générer le PDF et le stocker."""
    print(f"⚙️ [WORKER] Début de la génération du PDF pour la commande : {order_id}")
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. On appelle ta fonction qui crée le PDF avec les QR codes fixes
            pdf_buffer = await generate_order_pdf_in_memory(order_id, db)
            
            if pdf_buffer:
                # 2. Stockage des octets bruts directement dans la RAM de Redis (Valable 1 heure)
                await redis_conn.setex(
                    f"pdf_cache:{order_id}", 
                    3600, 
                    pdf_buffer.getvalue()
                )
                
                # 3. On met à jour le statut en base de données
                result = await db.execute(select(Order).where(Order.id == order_id))
                order = result.scalar_one_or_none()
                if order:
                    order.is_pdf_ready = True # l'etat du pdf pres
                    await db.commit()
                    
                print(f"✅ [WORKER] Succès : PDF pour {order_id} placé dans le cache Redis.")
            else:
                print(f"❌ [WORKER] Échec : Le buffer PDF est vide pour {order_id}")
                
        except Exception as e:
            print(f"💥 [WORKER] Crash pendant la génération pour {order_id} : {str(e)}")

async def generate_ticket_pdf_task(ctx, ticket_id: str, order_id: str):
    """Tâche ARQ exécutée en arrière-plan pour générer le PDF d'un SEUL ticket et le stocker."""
    print(f"⚙️ [WORKER] Début de la génération du PDF pour le TICKET : {ticket_id} (Commande : {order_id})")
    
    async with AsyncSessionLocal() as db:
        try:
            # 1. On appelle ta fonction qui crée le PDF pour ce ticket précis
            pdf_buffer = await generate_ticket_pdf_in_memory(ticket_id, order_id, db)
            
            if pdf_buffer:
                # 2. 🎯 CORRECTION CLÉ REDIS : On stocke avec l'ID du TICKET, pas de la commande !
                # Sinon, les billets d'une même commande vont s'écraser entre eux.
                await redis_conn.setex(
                    f"ticket_pdf_cache:{ticket_id}", 
                    3600, 
                    pdf_buffer.getvalue()
                )
                
                # 3. 🎯 CORRECTION STATUT BDD : On met à jour l'état du TICKET, pas de la commande !
                # C'est le ticket qui est prêt à être téléchargé individuellement.
                result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
                ticket = result.scalar_one_or_none()
                if ticket:
                    ticket.is_pdf_ready = True # Assure-toi d'avoir ce champ sur ton modèle Ticket
                    await db.commit()
                    
                print(f"✅ [WORKER] Succès : PDF pour le ticket {ticket_id} placé dans le cache Redis.")
            else:
                print(f"❌ [WORKER] Échec : Le buffer PDF est vide pour le ticket {ticket_id}")
                
        except Exception as e:
            print(f"💥 [WORKER] Crash pendant la génération pour le ticket {ticket_id} : {str(e)}")

# Configuration obligatoire pour ARQ
class WorkerSettings:
    functions = [generate_pdf_task,generate_ticket_pdf_task]
    redis_settings = REDIS_SETTINGS