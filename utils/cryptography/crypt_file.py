import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# On charge les variables du fichier .env
load_dotenv()

# On récupère la clé. 
# En bonus : si elle n'est pas dans le .env, on met une clé de secours pour éviter que l'app plante.
QR_KEY_RAW = os.getenv("cryptage_key", "W-EQefVNgytaDqQ_8XPJDhIHlUzbd0liFW_Du4sLZwQ=")

# On initialise la suite de cryptage Fernet (elle prend des bytes en entrée)
cipher_suite = Fernet(QR_KEY_RAW.encode())

def encrypt_token(raw_token: str) -> str:
    """Crypte le token pour le mettre en sécurité dans le QR Code"""
    encrypted_bytes = cipher_suite.encrypt(raw_token.encode('utf-8'))
    return encrypted_bytes.decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """Décrypte le QR code lors du scan pour retrouver le token original"""
    decrypted_bytes = cipher_suite.decrypt(encrypted_token.encode('utf-8'))
    return decrypted_bytes.decode('utf-8')