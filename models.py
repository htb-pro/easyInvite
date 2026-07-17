from sqlalchemy import Column,String,Integer,DateTime,Text,Uuid,Date,ForeignKey,Boolean,UniqueConstraint,Table,Float,JSON
import uuid
from sqlalchemy.orm import relationship
from db_setting import Base
from uuid import uuid4
from datetime import datetime,timezone


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
    created_at = Column(DateTime,default=datetime.utcnow)

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
    name= Column(String(50),index=True)
    type = Column(String(50))
    date = Column(DateTime)
    address =Column(String(255))
    location =Column(String(50))
    description = Column(Text,nullable=True)
    created_date =Column(DateTime,default=datetime.utcnow)
    state = Column(String,default="en attente")
    couple_name = Column(String(50))
    couple_phone_number= Column(String(15))
    guest_present = Column(Boolean,default=False)
    created_by = Column(String,ForeignKey("users.id"))
    group_id= Column(String,ForeignKey("groups.id"))
    organizer_id = Column(String, ForeignKey("organizers.id", ondelete="SET NULL"), nullable=True)
    organizer = Column(String(255))#organisateur d'evenement
    greeting_message = Column(Text,nullable=True)#message d'accueil d'invite
    photo_url=Column(String(255),nullable=True)
    photo_public_id=Column(String(255),nullable=True)
    language = Column(String(50),default="fr")#langue par defaut de l'evenement
    total_capacity = Column(Integer)#capacité totale de place de l'evenement
    city = Column(String(100),nullable=True) #la ville de l'evenement
    sold_seats = Column(Integer,default=0)#nombre de places vendues
    is_featured = Column(Boolean, default=False, nullable=True)#LE CHAMP CLÉ : False par défaut, l'admin le passe à True pour le mettre À la Une
    is_deleted =Column(Boolean, default=False, nullable=True)

    guests = relationship("Guest",back_populates="event",cascade="all,delete")
    groups = relationship("Group",back_populates ="events")
    orders = relationship("Order",back_populates ="events")
    tickets = relationship("Ticket",back_populates ="events")
    ticket_prices= relationship("Ticket_price",back_populates ="events")
    organizers = relationship("Organizer", back_populates="events")

class Guest(Base):
    __tablename__="guests"
    id  = Column(String,primary_key=True,unique=True,default=lambda:str(uuid4()))
    name  = Column(String(60))
    guest_type  = Column(String(20))
    telephone =  Column(String,nullable=False) 
    email = Column(String,nullable=True)
    place  = Column(String,nullable=True)
    event_id  = Column(String,ForeignKey('events.id'),nullable=False)
    created_date  = Column(DateTime,default=datetime.utcnow)
    is_present  = Column(Boolean,default=False)
    whatsapp_status = Column(String,default="pending")
    qr_token  = Column(String,unique=True,nullable=False,default=lambda : str(uuid4()),index=True)
    get_pass = Column(String,unique=True,default=lambda : str(uuid4()),index=True)
    photo_url=Column(String(255),nullable=True)
    photo_public_id=Column(String(255),nullable=True)
    
    event = relationship("Event",back_populates="guests")
    invite = relationship("Invite",back_populates="guest",uselist = False,cascade="all,delete-orphan")
    __table_args__ = (
        UniqueConstraint('email', 'event_id', name='uix_email_event'),
        UniqueConstraint('telephone', 'event_id', name='uix_telephone_event'),
    )
class PresenceConfirmation(Base):
    __tablename__ = "guestPresence"
    id  = Column(String,primary_key=True,unique=True,default=lambda:str(uuid4()))
    guest_id  = Column(String,ForeignKey("guests.id") ,nullable = False,index=True)
    invite_id = Column(String,ForeignKey("invites.id") ,nullable = False)
    response  =Column(String,nullable = False)
    comment=Column(String)
    send_at  = Column(DateTime,default=datetime.utcnow)

    invite = relationship("Invite",back_populates = "guestResponse",uselist=False)

class Invite(Base):
    __tablename__ = "invites"
    
    id = Column(String, primary_key=True, unique=True, default=lambda: str(uuid4()))
    guest_id = Column(String, ForeignKey('guests.id', ondelete="CASCADE"), unique=True, nullable=False)
    qr_token = Column(String, unique=True, nullable=False, default=lambda: str(uuid4()), index=True)
    created_date = Column(DateTime, default=datetime.utcnow)
    is_used = Column(Boolean, default=False)
    used_at = Column(DateTime, nullable=True)
    guest = relationship("Guest", back_populates="invite")
  

    guest=relationship("Guest",back_populates="invite",uselist=False)
    guestResponse=relationship("PresenceConfirmation",back_populates="invite",cascade = "all,delete-orphan",uselist=False)

#--------------------------------------------e-ticket tables---------------------------------------------
class ExternalUser(Base):
    __tablename__ = "external_users"
    id = Column(String,primary_key = True,default = lambda : str(uuid4()))
    phone_number = Column(String, unique=True, index=True)
    email = Column(String(150), nullable=True)
    name = Column(String)
    password = Column(String, nullable=False)  #le mot de passe doit etre hasher  avant de le stocker
    created_at = Column(DateTime,default=datetime.utcnow)
     # Gestion de Compte & Sécurité
    is_active = Column(Boolean, default=True)  

    orders = relationship("Order", back_populates="external_user")
    ext_user = relationship("OTP", back_populates="current_otp",uselist=False)#external user

class OTP(Base):
    __tablename__ = "otps"
    id = Column(String, primary_key=True,default = lambda : str(uuid4()))
    ext_user_id = Column(String, ForeignKey('external_users.id', ondelete="CASCADE"), nullable=True) #la cle etrangere de external_user_id
    organizer_id = Column(String, ForeignKey('organizers.id', ondelete="CASCADE"), nullable=True) #la cle etrangere de organizer_id
    code = Column(String)
    otp_attempts = Column(Integer, default=0) # Sécurité pour bloquer après 3 essais ratés
    expires_at = Column(DateTime) # Très important pour la sécurité l'expiration du code otp

    current_otp = relationship("ExternalUser", back_populates="ext_user")
    organisers = relationship("Organizer", back_populates="org_otp")

class Organizer(Base):
    __tablename__ = "organizers"

    id = Column(String,primary_key = True,default = lambda : str(uuid4()))
    #  Informations de Profil & Connexion
    company_name = Column(String, nullable=False, index=True)  # Nom de l'agence ou de l'organisateur
    email = Column(String, unique=True, nullable=False, index=True)
    phone_number = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    # Gestion de Compte & Sécurité
    is_active = Column(Boolean, default=True)      # Permet de bloquer un compte si besoin
    is_verified = Column(Boolean, default=False)  # Pour la validation des documents/identité en prod
    created_at = Column(DateTime, default=datetime.utcnow)

    # 🔗 RELATION 1 à N (Un organisateur possède plusieurs événements)
    # user.events renverra la liste de tous ses événements
    events = relationship(
        "Event", 
        back_populates="organizers",
    )
    org_otp = relationship("OTP", back_populates="organisers")

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, index=True,default = lambda :str(uuid4()))
    event_id = Column(String,ForeignKey("events.id",ondelete="CASCADE"),nullable=False,index=True)
    user_id = Column(String, ForeignKey("external_users.id",ondelete="SET NULL"), nullable=True,index=True)
    buyer_name = Column(String, nullable=False)
    buyer_number = Column(String, nullable=False,index=True)
    ticket_type= Column(String(15))
    ticket_quantity = Column(Integer,  nullable=False)#nombre de billet
    total_amount = Column(Float, nullable=False)
    devise = Column(String)
    transaction_id =Column(String, nullable=False)
    paid = Column(Boolean, default=False)
    creation = Column(DateTime,default=datetime.utcnow)
    is_pdf_ready = Column(Boolean, default=False)#l'etat du billet vrai si la generation a pris fin sinon faux
    downloaded =Column(Boolean, default=False) #determine si les billets on etait deja telcharger 

    events = relationship("Event",back_populates="orders")
    tickets = relationship("Ticket", back_populates="orders", cascade="save-update")
    external_user = relationship("ExternalUser", back_populates="orders")

class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(String, primary_key=True, index=True,default=lambda : str(uuid4()))
    order_id = Column(String, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True,index=True) # Lié à la commande financière
    event_id = Column(String, ForeignKey("events.id",ondelete="CASCADE"), index=True)
    type= Column(String(15))
    seri = Column(String(25))#la serie du ticket
    number = Column(Integer) #numero du ticket
    participator_name = Column(String(50))      # Nom de la personne qui détient ce ticket précis
    participator_number = Column(String(20),index=True)      # Numero du payeur
    qr_token = Column(String, unique=True,index = True) # Token unique crypté dans le QR Code
    get_pass = Column(String,index=True)          # Code de secours (8 caractères)
    totp_secret = Column(String(32), nullable=True)#l'totp
    is_scanned = Column(Boolean, default=False) # Pour le contrôle à l'entrée
    creation = Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    
    orders = relationship("Order", back_populates="tickets")
    events = relationship("Event",back_populates="tickets")

class Ticket_price(Base):
    __tablename__="ticket_prices"
    id = Column(String, primary_key=True, index=True,default = lambda :str(uuid4()))
    event_id = Column(String, ForeignKey("events.id",ondelete="CASCADE"))
    ticket_type= Column(String(50))
    price = Column(Float, nullable=False)
    device= Column(String(15))

    events = relationship("Event",back_populates="ticket_prices")

#--------------------------------------------e-event tables---------------------------------------------
class EventRequest(Base):
    __tablename__ = 'event_requests'
    id = Column(String, primary_key=True, index=True,default = lambda :str(uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    event_type = Column(String(50), nullable=False) # Étape 1 : Type d'événement (prive, professionnel, public, cle_en_main)
    guest_count = Column(String(20), nullable=False)  # Stocke "0-50", "50-150", "150-500", "500+"
    event_city = Column(String(100), nullable=False)   # Kinshasa, Lubumbashi, etc.
    cadre_lieu = Column(String(50), nullable=True)     # Nullable si l'utilisateur choisit "clé en main" direct   
    services = Column(JSON, nullable=True) # Stockera un tableau JSON comme : ["deco", "sonorisation", "mc"]

    # Étape 4 : Coordonnées du visiteur
    client_name = Column(String(150), nullable=False)
    client_phone = Column(String(30), nullable=False)
    