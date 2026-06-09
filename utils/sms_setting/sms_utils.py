import os, africastalking,requests
from dotenv import load_dotenv
from config import africa_talking_key

# Chargement des variables d'environnement
load_dotenv()

username =  "sandbox"
api_key = africa_talking_key

# 🎯 LE PATCH MAGIQUE : On force l'environnement à ignorer les restrictions SSL locales
os.environ['CURL_CA_BUNDLE'] = ''
requests.packages.urllib3.disable_warnings() # Cache les avertissements rouges dans la console

# On crée une méthode patchée pour s'assurer que TOUTES les requêtes sortantes ignorent le SSL en Dev
old_request = requests.Session.request
def new_request(*args, **kwargs):
    kwargs['verify'] = False # Désactive la vérification stricte du certificat SSL
    return old_request(*args, **kwargs)
requests.Session.request = new_request

# Initialisation du SDK Africa's Talking
africastalking.initialize(username, api_key)
sms = africastalking.SMS

async def send_otp_sms(phone_number: str, otp_code: str):
    """
    Envoie le code OTP au simulateur ou au vrai téléphone.
    phone_number doit être au format '243XXXXXXXXX'
    """
    message = f"Votre code de vérification e-ticket est : {otp_code}. Il expire dans 5 minutes."
    
    # Africa's Talking exige le signe '+' pour le format international
    recipients = [f"+{phone_number}"]
    
    try:
        # Envoi du SMS
        response = sms.send(message, recipients)
        print(f"--- [SMS SUCCESS] Reponse Africa's Talking : {response}")
        return True
    except Exception as e:
        print(f"--- [SMS ERROR] Echec de l'envoi : {e}")
        print(f"-----------------------------------{africa_talking_key}")
        return False