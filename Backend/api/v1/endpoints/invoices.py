import os
import uuid
import boto3
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.orm import Session
from schemas.invoice import SubmitIdRequest
from db.session import get_db
from models.user import User
from models.invoice import Invoice
from services.ocr_service import extract_text_pdfplumber, extract_text_ocr, extract_data
from core.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME

router = APIRouter()

s3_client = boto3.client(
    's3',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

@router.post('/submit-id')
async def submit_id(req: SubmitIdRequest, db: Session = Depends(get_db)):
    user_id = req.id
    if not user_id:
        raise HTTPException(status_code=400, detail="ID is required")

    try:
        existing_user = db.query(User).filter(User.user_id == user_id).first()
        if not existing_user:
            new_user = User(user_id=user_id)
            db.add(new_user)
            db.commit()
        return {"success": True, "message": f"ID {user_id} securely saved to the Database!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/upload-pdf')
async def upload_pdf(pdfDocument: UploadFile = File(...), userId: str = Form("Unknown"), db: Session = Depends(get_db)):
    if not pdfDocument.filename:
        raise HTTPException(status_code=400, detail="Empty filename")

    filename = f"{uuid.uuid4()}_{pdfDocument.filename}"
    local_path = os.path.join("/tmp" if os.name != 'nt' else os.environ.get('TEMP', 'C:\\temp'), filename)
    
    file_bytes = await pdfDocument.read()
    with open(local_path, "wb") as f:
        f.write(file_bytes)
    
    try:
        s3_key = f"invoices/{filename}"
        s3_client.upload_file(local_path, S3_BUCKET_NAME, s3_key)
        s3_url = f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        
        text = extract_text_pdfplumber(local_path)
        if not text.strip():
            text = extract_text_ocr(local_path)
            
        extracted_data = extract_data(text)
        
        new_invoice = Invoice(
            user_id=userId,
            pdf_s3_url=s3_url,
            invoice_no=extracted_data.get("Invoice No", ""),
            date=extracted_data.get("Date", ""),
            amount=str(extracted_data.get("Amount", ""))
        )
        db.add(new_invoice)
        db.commit()
        db.refresh(new_invoice)
        invoice_id = new_invoice.id
        
        if os.path.exists(local_path):
            os.remove(local_path)
            
        return {
            "success": True,
            "data": {
                "Record ID": invoice_id,
                "User ID": userId,
                "Invoice Number": extracted_data.get("Invoice No", "Not Found"),
                "Date": extracted_data.get("Date", "Not Found"),
                "Amount": extracted_data.get("Amount", "Not Found")
            }
        }
        
    except Exception as e:
        db.rollback()
        if os.path.exists(local_path):
            os.remove(local_path)
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/update-invoice/{invoice_id}')
async def update_invoice(invoice_id: int, data: dict, db: Session = Depends(get_db)):
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    user_id = data.get("User ID")
    invoice_no = data.get("Invoice Number")
    date_val = data.get("Date")
    amount = data.get("Amount")

    try:
        invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
            
        invoice.user_id = user_id
        invoice.invoice_no = invoice_no
        invoice.date = date_val
        invoice.amount = str(amount)
        db.commit()
        return {"success": True, "message": "Invoice properly updated in database!"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
