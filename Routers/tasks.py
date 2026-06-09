import os,io,base64,qrcode
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from models import Order
from utils.cryptography.crypt_file import encrypt_token
from xhtml2pdf import pisa
from jinja2 import Environment, FileSystemLoader
from xhtml2pdf import pisa


env = Environment(loader=FileSystemLoader("templates"))

def xhtml2pdf_link_callback(uri, rel):
    if uri.startswith("data:image"):
        return uri
        
    # On construit le chemin absolu
    path = os.path.join(os.getcwd(), uri)
    
    # PETIT TEST DE SÉCURITÉ : Est-ce que le fichier existe vraiment ?
    if not os.path.exists(path):
        print(f"⚠️ ERREUR CRITIQUE : Fichier introuvable à l'emplacement : {path}")
    else:
        print(f"✅ SUCCÈS : L'image a été trouvée ici : {path}")
        
    return path

#generation du billet 
def generer_qr_code_base64(qr_token: str) -> str:
    crypted_token = encrypt_token(qr_token)
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(crypted_token)
    qr.make(fit=True)
    
    img_byte_arr = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(img_byte_arr, format='PNG')
    return base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')



#fonction qui verifier l'etat du pdf et mettre a jour la db
async def process_ticket_generation(order_id: str, ticket_data: dict, db: AsyncSession):
    try:
        # 1. Génération du PDF en RAM (via ta fonction generate_ticket_pdf)
        pdf_buffer = await generate_ticket_pdf(ticket_data)
        
        if pdf_buffer:
            # 2. Mise à jour du statut en base de données
            # On récupère à nouveau l'objet pour être sûr d'avoir la session active
            stmt = select(Order).where(Order.id == order_id)
            result = await db.execute(stmt)
            order = result.scalar_one()
            
            order.is_pdf_ready = True
            await db.commit() # Sauvegarde du statut
            
    except Exception as e:
        print(f"Erreur lors de la génération en fond : {e}")

# la fonction donnant l'etat du pdf genere ou non
async def generate_and_save_pdf(ticket_data: dict, output_path: str):
    """
    Fonction lourde qui tourne en arrière-plan.
    """
    pdf_buffer = await generate_ticket_pdf(ticket_data) # Ta fonction actuelle
    if pdf_buffer:
        with open(output_path, "wb") as f:
            f.write(pdf_buffer.getvalue())
        return True
    return False

#fonction pour la verification du paiement de la commande et la generation du billet
async def is_order_ready(order_id: str, db: AsyncSession):
    # 1. Récupération de la commande depuis la base
    stmt = select(Order).where(Order.id == order_id)
        
        # OPTIONNEL : Si tu as besoin de vérifier le nombre de tickets dans la page, 
        # garde le selectinload, sinon retire-le pour aller plus vite.
        # stmt = stmt.options(selectinload(Order.tickets))
        
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    
    if not order:
        return False, None
    
    # 2. Vérification : Payé ET Statut de génération à True
    # Plus besoin d'os.path.exists, on utilise notre flag en base
    if order.paid and order.is_pdf_ready:
        return True, order
        
    return False, order


from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

async def get_order_from_db(order_id: str, db: AsyncSession):
    """
    Récupère une commande par son ID.
    On utilise selectinload uniquement si on a besoin des tickets,
    sinon on peut le retirer pour gagner en performance.
    """
    try:
        # On fait une requête simple pour chercher la commande
        stmt = select(Order).where(Order.id == order_id)
        
        # OPTIONNEL : Si tu as besoin de vérifier le nombre de tickets dans la page, 
        # garde le selectinload, sinon retire-le pour aller plus vite.
        # stmt = stmt.options(selectinload(Order.tickets))
        
        result = await db.execute(stmt)
        order = result.scalar_one_or_none()
        
        return order
        
    except Exception as e:
        print(f"Erreur lors de la récupération de la commande {order_id}: {e}")
        return None