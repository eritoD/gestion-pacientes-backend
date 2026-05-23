import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gestion_pacientes.db")

# Para PostgreSQL en producción, agregar pool_size y max_overflow
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
pool_kwargs = {} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {"pool_size": 5, "max_overflow": 10}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args, **pool_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
