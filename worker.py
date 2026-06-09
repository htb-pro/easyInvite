from db_setting import AsyncSessionLocal
from utils.redis_config import redis_conn
from Routers.ticket import generate_order_pdf_in_memory
from Routers.tasks import get_order_from_db # Assure-toi que cette fonction existe et utilise 'db'
from config import REDIS_SETTINGS
from sqlalchemy import select
from models import Order

# La fonction de tâche appelée par le Worker ARQ
async def generate_pdf_task(ctx, order_id: str):
    # 1. Ouverture correcte de la session (tu avais oublié les parenthèses)
    async with AsyncSessionLocal() as db:
        
        # 2. Génération du PDF
        pdf_buffer = await generate_order_pdf_in_memory(order_id, db)
        
        if pdf_buffer:
            # 3. Stockage dans Redis (RAM)
            # On utilise le pool Redis déjà configuré dans ton projet
            await redis_conn.setex(
                f"pdf_cache:{order_id}", 
                3600, 
                pdf_buffer.getvalue()
            )
            
            # 4. Mise à jour de la DB pour dire que c'est prêt
            # On récupère l'objet (ou on fait un update direct)
            result = await db.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one_or_none()
            if order:
                order.is_pdf_ready = True # Attention à ton nom de champ réel !
                await db.commit()
                print(f"-------->Succès : PDF pour {order_id} est en cache.")
        else:
            print(f"---------->Erreur : La génération du PDF a échoué pour {order_id}")

# Configuration du Worker ARQ
class WorkerSettings:
    functions = [generate_pdf_task]
    redis_settings = REDIS_SETTINGS