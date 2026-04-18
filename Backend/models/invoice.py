from db.base import Base
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=True)
    pdf_s3_url = Column(String(500), nullable=True)
    invoice_no = Column(String(100), nullable=True)
    date = Column(String(100), nullable=True)
    amount = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
