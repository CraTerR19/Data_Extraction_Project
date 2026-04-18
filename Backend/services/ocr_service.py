import re
import pdfplumber
import pytesseract
from pdf2image import convert_from_path

INVOICE_NO_PATTERN = re.compile(
    r'(?:invoice\s*(?:no\.?|number|#)|receipt\s*(?:no\.?|number|id|#)|inv\s*(?:no\.?|#)|bill\s*(?:no\.?|number))'
    r'\s*[:\-#]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]+)', re.IGNORECASE)

DATE_PATTERN = re.compile(
    r'\b(?:'
    r'\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
    r'|\d{4}[\/\-]\d{2}[\/\-]\d{2}'
    r'|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}'
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}'
    r')\b', re.IGNORECASE)

AMOUNT_LABELLED_PATTERN = re.compile(
    r'(?:grand\s+total|total\s+amount|net\s+(?:payable|amount)|amount\s+(?:due|payable)|total(?:\s+fare)?)'
    r'\s*[:\-]?\s*'
    r'(?:₹|Rs\.?|INR|USD|\$)?\s*'
    r'([\d,]+(?:\.\d{1,2})?)', re.IGNORECASE)

AMOUNT_CURRENCY_PATTERN = re.compile(
    r'(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)', re.IGNORECASE)

def extract_text_pdfplumber(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: text += t + "\n"
    except Exception as e:
        print(f"pdfplumber Error: {e}")
    return text

def extract_text_ocr(pdf_path):
    text = ""
    try:
        images = convert_from_path(pdf_path)
        for img in images:
            text += pytesseract.image_to_string(img) + "\n"
    except Exception as e:
        print(f"OCR Error: {e}")
    return text

def extract_data(text):
    result = {"Invoice No": "Not Found", "Date": "Not Found", "Amount": "Not Found"}
    
    clean_text = re.sub(r'[^\x00-\x7F\u20B9]+', ' ', text)
    #Removes emojis, weird characters and non-English symbols
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    #Removes extra whitespace and newlines 

    m = INVOICE_NO_PATTERN.search(clean_text)
    if m: result["Invoice No"] = m.group(1).strip()

    m = DATE_PATTERN.search(clean_text)
    if m: result["Date"] = m.group(0).strip()

    m = AMOUNT_LABELLED_PATTERN.search(clean_text)
    if m:
        result["Amount"] = m.group(1).strip()
    else:
        curr_matches = AMOUNT_CURRENCY_PATTERN.findall(clean_text)
        curr_amounts = []
        for match in curr_matches:
            try:
                curr_amounts.append(float(match.replace(',', '').strip('.')))
            except ValueError:
                pass
        if curr_amounts:
            result["Amount"] = f"{max(curr_amounts):.2f}"

    return result
