from pydantic import BaseModel
from datetime import date
from typing import Optional

class eventForm(BaseModel):
    name :str
    date : date
    address :str
    description:Optional[str]
    state: str

class Guest(BaseModel):
    nom :  str
    guest_type :  str
    telephone :   str
    email: Optional[str] = None
    event : str




