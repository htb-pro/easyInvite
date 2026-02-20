from dotenv import load_dotenv
import os

load_dotenv()

secret = os.getenv('SECRET')#le secret ou sinature du token
algo = os.getenv('ALGO')#type d'algorithme
token_expire_minute = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTE',60))#duree d'expiration du token

