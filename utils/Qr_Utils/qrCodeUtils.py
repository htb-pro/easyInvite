import qrcode 
from qrcode import QRCode
import os


def createQrCode(token) -> str : 
    qr_dirs = "static/Pictures/guestQrCode" #le chemin du repertoir ou seront stocke les images (qrCode)
    filename = f"{token}.png" #le nom du qrCode
    file_path = os.path.join(qr_dirs,filename)
    url = f"http://localhost:8000/checkIn/{token}" #l'addresse ou sera stocker les qrcodes
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

def createInviteQrCode(Itoken):
    url = f"http://127.0.0.1:8000/{Itoken}"
    path = "static/Pictures/inviteQrCode"
    filename = f"{Itoken}.png" #Invite token 
    file_path = os.path.join(path,filename)
    qr = QRCode(
        version=1,
        error_correction = qrcode.constants.ERROR_CORRECT_H,
        box_size=2,
        border=3
    )
    qr.add_data(url)
    img = qr.make_image(fill_color="black",back_color="white")
    img.save(file_path)