from sqlalchemy import Column,String,Integer,DateTime,Text,Enum,Date,ForeignKey,Boolean,UniqueConstraint
import enum
from sqlalchemy.orm import relationship
from db_setting import Base
from uuid import uuid4
from datetime import datetime
class Event(Base): #event table
    __tablename__="events"
    id = Column(String,primary_key=True,unique=True,default=lambda :str(uuid4()))
    name = Column(String(50))
    type = Column(String(50))
    date = Column(Date)
    address = Column(String(50))
    description = Column(Text,nullable=True)
    created_date = Column(DateTime,default=datetime.now())
    state = Column(String,default="en cours")
    
    guests = relationship("Guest",back_populates="event",cascade="all,delete")

class Guest(Base):
    __tablename__="guests"
    id = Column(String,primary_key=True,unique=True,default=lambda:str(uuid4()))
    name = Column(String(60))
    guest_type = Column(String(20))
    telephone =  Column(String,nullable=False) 
    email= Column(String,nullable=True)
    place = Column(String,nullable=True)
    event_id = Column(String,ForeignKey('events.id'),nullable=False)
    created_date = Column(DateTime,default=datetime.now())
    is_present = Column(Boolean,default=False)
    qr_token = Column(String,unique=True,nullable=False,default=lambda : str(uuid4()))

    event = relationship("Event",back_populates="guests")
    invite = relationship("Invite",back_populates="guest",uselist = False,cascade="all,delete-orphan")
    __table_args__ = (
        UniqueConstraint('email', 'event_id', name='uix_email_event'),
        UniqueConstraint('telephone', 'event_id', name='uix_telephone_event'),
    )
class Invite(Base):
    __tablename__= "invites"
    id=Column(String,primary_key=True,unique=True,default = lambda :str(uuid4()))
    guest_id = Column(String,ForeignKey('guests.id',ondelete="CASCADE"))
    event_id = Column(String,ForeignKey('events.id',ondelete="CASCADE"))
    qr_token = Column(String,unique=True, default=lambda:str(uuid4()))
    created_date = Column(DateTime,default=datetime.now())
    is_used = Column(Boolean,default = False)
    used_at = Column(DateTime,default=datetime.now())


    guest=relationship("Guest",back_populates="invite",uselist=False)

