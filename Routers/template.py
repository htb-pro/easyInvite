from fastapi.templating import Jinja2Templates
from app.security.permissions import has_permission

templates = Jinja2Templates(directory="Templates")

templates.env.globals["has_permission"]  = has_permission