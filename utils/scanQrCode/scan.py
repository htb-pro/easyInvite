from pyzbar.pyzbar import decode
from PIL import Image

def scan_qr_code(filename:str):
    img = Image.open(filename)
    codes = decode(img)
    for code in codes : 
        contenu = code.data.decode("utf-8")
        print("le qrCode detecte : ",contenu)
        return contenu
    print("aucun qrCode detecte")
    