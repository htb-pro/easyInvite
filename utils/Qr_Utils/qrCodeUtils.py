import qrcode 
from qrcode import QRCode
import os


INVITE_FOLDER= "static/Pictures/inviteQrCode"

def createQrCode(token) -> str : 
    qr_dirs = "static/Pictures/guestQrCode" #le chemin du repertoir ou seront stocke les images (qrCode)
    filename = f"{token}.png" #le nom du qrCode
    file_path = os.path.join(qr_dirs,filename)
    url = f"{token}" #l'addresse ou sera stocker les qrcodes
    qr = QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size = 2,
        border=3,
    )
    qr.add_data(url)
    img = qr.make_image(fill_color = "black",back_color="white")
    img.save(file_path)
    return filename

def createInviteQrCode(Itoken,event,guest,guest_name,guest_tel):
    event_folder = os.path.join(INVITE_FOLDER,f"Event_{event}")
    os.makedirs(event_folder,exist_ok=True)
    url = f"http://easyinvite-1.onrender.com/invite/{event}/{guest}/create"
    filename = f"{guest_name}-{guest_tel}.png" #Invite token 
    file_path = os.path.join(event_folder,filename)
    qr = QRCode(
        version=1,
        error_correction = qrcode.constants.ERROR_CORRECT_H,
        box_size=2,
        border=3
    )
    qr.add_data(url)
    img = qr.make_image(fill_color="black",back_color="white")
    img.save(file_path)
