import pymysql
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import DATABASE_URL, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def initialize_db():
    # Only need to create database if it doesn't exist, as SQLAlchemy creates tables
    conn = None
    try:
        conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
        conn.commit()
    except Exception as e:
        print(f"Could not initialize DB (Ignore if testing without DB): {e}")
    finally:
        if conn:
            conn.close()

    # Now create tables via SQLAlchemy Base
    from db.base import Base
    import models  # This registers the models
    Base.metadata.create_all(bind=engine)
