from sqlalchemy import Column, Integer, String, Boolean
from db_setting import Base

class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    event_name = Column(String, nullable=False)
    buyer_name = Column(String, nullable=False)
    buyer_email = Column(String, nullable=False)
    amount = Column(Integer, nullable=False)
    paid = Column(Boolean, default=False)
    tx_ref = Column(String, unique=True, nullable=True)