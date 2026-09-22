from pydantic import BaseModel,EmailStr, HttpUrl
from datetime import date
from typing import Optional,List
from uuid import UUID


class EventPictureCreate(BaseModel):
    event_id: str
    url: HttpUrl  # Valide automatiquement qu'il s'agit d'un format d'URL correct
    csrf_token: Optional[str] = None

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

class PermissionBase(BaseModel):
    name: str

class Permission(PermissionBase):
    id: UUID
    class Config:
        orm_mode = True

class RoleBase(BaseModel):
    name: str

class Role(RoleBase):
    id: UUID
    permissions: List[Permission] = []
    class Config:
        orm_mode = True

class UserBase(BaseModel):
    email: EmailStr
    is_active: bool

class User(UserBase):
    id: UUID
    roles: List[Role] = []
    class Config:
        orm_mode = True

class Group(BaseModel):
    name: str

#dfonction pour la suppression d'image
class DeleteImageRequest(BaseModel):
    public_id: str