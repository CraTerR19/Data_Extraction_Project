import pdfplumber
import re
import tkinter as tk
from tkinter import filedialog, messagebox
import os


# -------------------------------
# Function to select PDF
# -------------------------------
def select_pdf():
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select Invoice PDF",
        filetypes=[("PDF Files", "*.pdf")]
    )

    return file_path


# -------------------------------
# OCR fallback (for scanned PDFs)
# -------------------------------
def ocr_pdf(pdf_path):
    text = ""
    images = convert_from_path(pdf_path)
    for img in images:
        text += pytesseract.image_to_string(img)
    return text


# -------------------------------
# Function to extract data
# -------------------------------
def extract_invoice_data(pdf_path):
    text = ""

    # Try extracting text normally
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        return {"Error": f"Error reading PDF: {e}"}

    # If text is empty → use OCR
    if not text.strip() and OCR_AVAILABLE:
        print("Using OCR (Scanned PDF detected)...")
        text = ocr_pdf(pdf_path)

    # -------------------------------
    # CLEAN TEXT (IMPORTANT)
    # -------------------------------
    text = text.replace("\n", " ")
    text = re.sub(r'\s+', ' ', text)

    print("\n--- CLEANED TEXT ---\n", text)

    # -------------------------------
    # REGEX PATTERNS
    # -------------------------------

    # Invoice Number
    invoice_patterns = [
        r'Invoice\s*(No|Number|#)?\s*[:\-]?\s*([A-Z0-9\-\/]+)',
        r'Inv\s*#\s*[:\-]?\s*([A-Z0-9\-\/]+)',
        r'Bill\s*(No|Number)?\s*[:\-]?\s*([A-Z0-9\-\/]+)'
    ]

    # Date
    date_patterns = [
        r'\b\d{2}[/-]\d{2}[/-]\d{4}\b',
        r'\b\d{4}[/-]\d{2}[/-]\d{2}\b',
        r'\b\d{1,2}\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{4}\b'
    ]

    # Amount
    amount_patterns = [
        r'(Grand\s*Total\s*[:\-]?\s*(₹|INR)?\s*[\d,]+\.\d{1,2})',
        r'(Net\s*Payable\s*[:\-]?\s*(₹|INR)?\s*[\d,]+\.\d{1,2})',
        r'(Amount\s*Due\s*[:\-]?\s*(₹|INR)?\s*[\d,]+\.\d{1,2})',
        r'(Total\s*(Amount)?\s*[:\-]?\s*(₹|INR)?\s*[\d,]+\.\d{1,2})',
        r'(₹\s*[\d,]+\.\d{1,2})',
        r'(INR\s*[\d,]+\.\d{1,2})'
    ]

    # -------------------------------
    # EXTRACTION LOGIC
    # -------------------------------

    # Invoice Number
    invoice_no = "Not Found"
    for pattern in invoice_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            invoice_no = match.group(match.lastindex)
            break

    # Date
    date = "Not Found"
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date = match.group(0)
            break

    # Amount
    amount = "Not Found"
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount = match.group(0)
            break

    # Smart fallback → get highest value
    if amount == "Not Found":
        numbers = re.findall(r'[\d,]+\.\d{2}', text)
        if numbers:
            amount = max(numbers, key=lambda x: float(x.replace(',', '')))

    return {
        "Invoice No": invoice_no,
        "Date": date,
        "Amount": amount
    }


# -------------------------------
# MAIN PROGRAM
# -------------------------------
def main():
    pdf_path = select_pdf()

    if not pdf_path:
        messagebox.showwarning("No File", "No PDF selected!")
        return

    print("\nSelected File:", pdf_path)

    # Open PDF
    try:
        os.startfile(pdf_path)
    except:
        print("Could not open PDF automatically.")

    # Extract data
    data = extract_invoice_data(pdf_path)

    print("\n--- Extracted Data ---")
    for key, value in data.items():
        print(f"{key}: {value}")

    # Show popup
    result_text = "\n".join([f"{k}: {v}" for k, v in data.items()])
    messagebox.showinfo("Extracted Invoice Data", result_text)


# Run program
if __name__ == "__main__":
    main()