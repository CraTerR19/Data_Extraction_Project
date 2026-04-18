import os
import re
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import pdfplumber
import pytesseract
from dotenv import load_dotenv

load_dotenv()

# -------------------------------
# 1. DOWNLOAD PDF FROM S3
# -------------------------------
def download_pdf_from_s3(s3_url):
    """Parses the S3 URL and downloads the file securely using boto3."""
    try:
        parsed_url = urllib.parse.urlparse(s3_url)
        host = parsed_url.netloc
        bucket_name = host.split('.s3.')[0]
        object_key = parsed_url.path.lstrip('/')

        local_file_path = 'temp_downloaded_invoice.pdf'

        s3 = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'ap-south-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )

        s3.download_file(bucket_name, object_key, local_file_path)
        print("Successfully downloaded PDF from S3")
        return local_file_path

    except ClientError as e:
        print(f"AWS Error downloading PDF: {e}")
        return None
    except Exception as e:
        print(f"General Error parsing URL or downloading: {e}")
        return None


# -------------------------------
# 2. EXTRACT TEXT USING PDFPLUMBER
# -------------------------------
def extract_text_pdfplumber(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        print(f"pdfplumber Error: {e}")
        return ""
    return text


# -------------------------------
# 3. OCR FALLBACK (SCANNED PDF)
# -------------------------------
def extract_text_ocr(pdf_path):
    text = ""
    try:
        images = convert_from_path(pdf_path)
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"
    except Exception as e:
        print(f"OCR Error: {e}")
    return text


# -------------------------------
# 4. REGEX PATTERNS
# -------------------------------

# Invoice / Receipt Number
# Matches: "Invoice No:", "Receipt No.", "Invoice #", "Inv No", "Receipt ID", "Bill No"
INVOICE_NO_PATTERN = re.compile(
    r'(?:invoice\s*(?:no\.?|number|#)|receipt\s*(?:no\.?|number|id|#)|inv\s*(?:no\.?|#)|bill\s*(?:no\.?|number))'
    r'\s*[:\-#]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]+)',
    re.IGNORECASE
)

# Date
# Matches: DD/MM/YYYY, MM/DD/YYYY, YYYY-MM-DD, DD-MM-YYYY, DD MMM YYYY, MMM DD YYYY
DATE_PATTERN = re.compile(
    r'\b(?:'
    r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
    r'|\d{4}[\/\-]\d{2}[\/\-]\d{2}'
    r'|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}'
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}'
    r')\b',
    re.IGNORECASE
)

# Amount
# Primary: labelled totals (Grand Total, Total Amount, Net Payable, Amount Due, etc.)
AMOUNT_LABELLED_PATTERN = re.compile(
    r'(?:grand\s+total|total\s+amount|net\s+(?:payable|amount)|amount\s+(?:due|payable)|total(?:\s+fare)?)'
    r'\s*[:\-]?\s*'
    r'(?:₹|Rs\.?|INR|USD|\$)?\s*'
    r'([\d,]+(?:\.\d{1,2})?)',
    re.IGNORECASE
)

# Fallback: any ₹ / Rs / INR symbol followed by a number
AMOUNT_CURRENCY_PATTERN = re.compile(
    r'(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)',
    re.IGNORECASE
)


# -------------------------------
# 5. EXTRACT DATA
# -------------------------------
def extract_data(text):
    result = {}

    # Invoice Number
    m = INVOICE_NO_PATTERN.search(text)
    result["Invoice No"] = m.group(1).strip() if m else "Not Found"

    # Date (first match is the invoice date)
    m = DATE_PATTERN.search(text)
    result["Date"] = m.group(0).strip() if m else "Not Found"

    # Amount — prefer labelled total, fall back to largest currency value on page
    m = AMOUNT_LABELLED_PATTERN.search(text)
    if m:
        result["Amount"] = m.group(1).strip()
    else:
        matches = AMOUNT_CURRENCY_PATTERN.findall(text)
        if matches:
            result["Amount"] = max(matches, key=lambda x: float(x.replace(',', '')))
        else:
            result["Amount"] = "Not Found"

    return result


# -------------------------------
# 6. MAIN FUNCTION
# -------------------------------
def process_invoice(url):
    print("Starting process...")

    pdf_path = download_pdf_from_s3(url)
    if not pdf_path:
        print("Failed to download PDF. Cannot continue.")
        return

    print("Extracting text using pdfplumber...")
    text = extract_text_pdfplumber(pdf_path)

    if not text.strip():
        print("No readable text found. Attempting OCR...")
        text = extract_text_ocr(pdf_path)

    if not text.strip():
        print("Could not extract any text from the PDF.")
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        return

    print("\n--- RAW TEXT ---\n")
    print(text)

    data = extract_data(text)

    print("\n--- EXTRACTED DATA ---")
    for k, v in data.items():
        print(f"{k}: {v}")

    if os.path.exists(pdf_path):
        os.remove(pdf_path)
        print("\nTemporary PDF file removed.")


# -------------------------------
# RUN
# -------------------------------
if __name__ == "__main__":
    url = "https://invoice-data-pdf-378371845166-ap-south-1-an.s3.ap-south-1.amazonaws.com/pdf/invoice.pdf"
    process_invoice(url)