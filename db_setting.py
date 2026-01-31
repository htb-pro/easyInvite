from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker,declarative_base
from sqlalchemy.engine import Engine
import sqlite3
#---------------------initialising
db_url = "sqlite:///easyInvite.db"
engine = create_engine(db_url,connect_args={"check_same_thread":False})
Base = declarative_base() #-----------------la classe mere pour la creation de table



@event.listens_for(Engine, "connect")
def enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        
localSession = sessionmaker(#creation de la session
    autocommit=False,
    autoflush=False,
    bind=engine
)

def connecting():
    db=localSession()
    try:
        yield db
    finally:
        db.close