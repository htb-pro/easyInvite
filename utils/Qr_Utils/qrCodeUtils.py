import qrcode 
from qrcode import QRCode
import os,io

def createInviteQrCode(event,guest):
    url = f"http://easyinvite-1.onrender.com/invite/{event}/{guest}/making" #les variables du lien sont l'id de l'evenement et celui de guest
    qr = QRCode(
        version=1,
        error_correction = qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=3
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black",back_color="white")
    memory = io.BytesIO()
    img.save(memory,format="PNG")
    memory.seek(0)
    return memory