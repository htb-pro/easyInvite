import qrcode 
from qrcode import QRCode
import os,io
from utils.cryptography.crypt_file import encrypt_token


def generateInviteQrCode(guest_id):
    secure_id = encrypt_token(guest_id) #on encrypte l'id de l'inviter
    qr = QRCode(
        version=1,
        error_correction = qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=3
    )
    qr.add_data(secure_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black",back_color="white")
    memory = io.BytesIO()
    img.save(memory,format="PNG")
    memory.seek(0)
    return memory

def createTicketQrCode(qr_token):#Qr code du billlet
    secure_id = encrypt_token(qr_token) #on encrypte l'id de l'inviter
    qr = QRCode(
        version=1,
        error_correction = qrcode.constants.ERROR_CORRECT_H,
        box_size=4,
        border=3
    )
    qr.add_data(secure_id)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black",back_color="white")
    memory = io.BytesIO()
    img.save(memory,format="PNG")
    memory.seek(0)
    return memory

