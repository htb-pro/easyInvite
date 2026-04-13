from sqlalchemy import Column,String,Integer,DateTime,Text,Uuid,Date,ForeignKey,Boolean,UniqueConstraint,Table
import uuid
from sqlalchemy.orm import relationship
from db_setting import Base
from uuid import uuid4
from datetime import datetime,date


def generate_serie(even_name:str):#la methode de creation de la serie d'un event
    words = even_name.split()
    serie = "".join(word[0].upper() for word in words if word)
    return serie
#---------------------tables ------------------
user_groups = Table(#association groupe et user
    "user_groups",
    Base.metadata,
    Column("user_id",ForeignKey("users.id"),primary_key = True),
    Column("group_id",ForeignKey("groups.id"),primary_key = True),
)
#permission <-> role
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id",ForeignKey("roles.id"),primary_key = True),
    Column("permission_id",ForeignKey("permissions.id"),primary_key = True),
)
#user <-> role
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id",ForeignKey("users.id"),primary_key = True),
    Column("role_id",ForeignKey("roles.id"),primary_key = True),
)
#groupe <-> role
group_roles = Table(
    "group_roles",
    Base.metadata,
    Column("group_id",ForeignKey("groups.id"),primary_key = True),
    Column("role_id",ForeignKey("roles.id"),primary_key = True),
)
class User(Base):
    __tablename__ = "users"
    id = Column(String,primary_key = True,default = lambda : str(uuid4()))
    name = Column(String)
    email = Column(String,unique = True,index=True,nullable = False)
    password = Column(String,nullable = False)
    state = Column(String,default="active")
    created_at = Column(DateTime,default=datetime.utcnow())

    #relationship
    groups = relationship("Group",secondary = user_groups,back_populates = "users")
    roles = relationship("Role",secondary = user_roles,back_populates = "users")

class Group(Base):
    __tablename__= "groups"
    id = Column(String,primary_key = True,default = lambda : str(uuid4()))
    name = Column(String,unique = True)

    #relationship
    users = relationship("User",secondary = user_groups,back_populates = "groups")
    roles = relationship("Role",secondary = group_roles,back_populates = "groups")
    events = relationship("Event",back_populates = "groups",cascade="all,delete")

class Role(Base):
    __tablename__ = "roles"
    id = Column(String,primary_key = True,default = lambda : str(uuid4()))
    name = Column(String,unique = True)

#relationship
    users = relationship("User",secondary = user_roles,back_populates = "roles")
    groups = relationship("Group",secondary = group_roles,back_populates = "roles")   
    permissions =  relationship("Permission",secondary = role_permissions,back_populates = "roles")

class Permission(Base):
    __tablename__ = "permissions"
    id = Column(String,primary_key = True,default = lambda : str(uuid4()))
    name = Column(String,unique = True)
    #relationship
    roles=  relationship("Role",secondary = role_permissions,back_populates = "permissions")

class Event(Base): #event table
    __tablename__="events"
    id = Column(String,primary_key=True,unique=True,default=lambda :str(uuid4()))
    name= Column(String(50))
    type = Column(String(50))
    date = Column(DateTime)
    address =Column(String(50))
    location =Column(String(50))
    description = Column(Text,nullable=True)
    created_date =Column(DateTime,default=datetime.now())
    state = Column(String,default="en attente")
    couple_name = Column(String(50))
    couple_phone_number= Column(String(15))
    guest_present = Column(Boolean,default=False)
    created_by = Column(String,ForeignKey("users.id"))
    group_id= Column(String,ForeignKey("groups.id"))
    programme = Column(Text,nullable=True)

    guests = relationship("Guest",back_populates="event",cascade="all,delete")
    groups = relationship("Group",back_populates ="events")

class Guest(Base):
    __tablename__="guests"
    id  = Column(String,primary_key=True,unique=True,default=lambda:str(uuid4()))
    name  = Column(String(60))
    guest_type  = Column(String(20))
    telephone =  Column(String,nullable=False) 
    email = Column(String,nullable=True)
    place  = Column(String,nullable=True)
    event_id  = Column(String,ForeignKey('events.id'),nullable=False)
    created_date  = Column(DateTime,default=datetime.now())
    is_present  = Column(Boolean,default=False)
    qr_token  = Column(String,unique=True,nullable=False,default=lambda : str(uuid4()))
    get_pass = Column(String,unique=True,default=lambda : str(uuid4()))

    event = relationship("Event",back_populates="guests")
    invite = relationship("Invite",back_populates="guest",uselist = False,cascade="all,delete-orphan")
    __table_args__ = (
        UniqueConstraint('email', 'event_id', name='uix_email_event'),
        UniqueConstraint('telephone', 'event_id', name='uix_telephone_event'),
    )
class PresenceConfirmation(Base):
    __tablename__ = "guestPresence"
    id  = Column(String,primary_key=True,unique=True,default=lambda:str(uuid4()))
    guest_id  = Column(String,ForeignKey("guests.id") ,nullable = False)
    invite_id = Column(String,ForeignKey("invites.id") ,nullable = False)
    response  =Column(String,nullable = False)
    comment=Column(String)
    send_at  = Column(DateTime,default=datetime.utcnow)

    invite = relationship("Invite",back_populates = "guestResponse",uselist=False)

class Invite(Base):
    __tablename__= "invites"
    id =Column(String,primary_key=True,unique=True,default = lambda :str(uuid4()))
    guest_id  =Column(String,ForeignKey('guests.id',ondelete="CASCADE"))
    qr_token  = Column(Uuid(as_uuid =True),unique=True, default=lambda:str(uuid4()))
    created_date  = Column(DateTime,default=datetime.now())
    is_used= Column(Boolean,default = False)
    used_at = Column(DateTime,default=datetime.now())
  

    guest=relationship("Guest",back_populates="invite",uselist=False)
    guestResponse=relationship("PresenceConfirmation",back_populates="invite",cascade = "all,delete-orphan",uselist=False)
