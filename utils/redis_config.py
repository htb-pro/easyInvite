import redis.asyncio as Redis
from config import redis_url # Tes infos de connexion (host, port, etc.)
# On crée une instance unique qui sera importée partout


from config import REDIS_SETTINGS
import redis.asyncio as redis

# On construit l'URL proprement
redis_url = redis_url

redis_conn = redis.from_url(redis_url, decode_responses=False)