"""
Invoice OCR Extractor
=====================
Extracts Invoice No., Amount, and Date from invoice images.

Strategy (layered for max accuracy):
  1. Preprocess image (deskew, denoise, upscale)
  2. Try Tesseract OCR + regex
  3. If confidence is low → fall back to Claude Vision API
  4. Return structured result as JSON

Requirements:
    pip install pytesseract pillow opencv-python anthropic
    Install Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
"""

import re
import sys
import json
import base64
import argparse
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytesseract

# ─── CONFIG ───────────────────────────────────────────────────────────────────

# If Tesseract is not in PATH, set the path manually:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Minimum Tesseract word-confidence to trust the result (0–100)
CONFIDENCE_THRESHOLD = 60

# Set to False if you don't want to use the Claude Vision fallback
USE_CLAUDE_FALLBACK = True

# ─── IMAGE PREPROCESSING ──────────────────────────────────────────────────────

def preprocess_image(image_path: str) -> np.ndarray:
    """
    Improve image quality before OCR:
    - Convert to grayscale
    - Upscale if small (Tesseract likes 300+ DPI)
    - Denoise
    - Adaptive threshold (handles uneven lighting)
    - Deskew
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Upscale if image is small
    h, w = gray.shape
    if w < 1200:
        scale = 1200 / w
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Adaptive threshold for better binarization
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )

    # Deskew
    binary = deskew(binary)

    return binary


def deskew(image: np.ndarray) -> np.ndarray:
    """Rotate image to correct skew using Hough line detection."""
    coords = np.column_stack(np.where(image < 127))
    if len(coords) < 100:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5:
        return image
    h, w = image.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return rotated


# ─── TESSERACT OCR ────────────────────────────────────────────────────────────

def run_tesseract(image: np.ndarray) -> tuple[str, float]:
    """
    Run Tesseract and return (full_text, avg_confidence).
    Uses --psm 6 (uniform block of text).
    """
    pil_img = Image.fromarray(image)
    config = "--psm 6 --oem 3"
    data = pytesseract.image_to_data(pil_img, config=config,
                                     output_type=pytesseract.Output.DICT)
    text = pytesseract.image_to_string(pil_img, config=config)

    # Average confidence of words with confidence > 0
    confs = [int(c) for c in data["conf"] if int(c) > 0]
    avg_conf = sum(confs) / len(confs) if confs else 0

    return text, avg_conf


# ─── REGEX FIELD EXTRACTION ───────────────────────────────────────────────────

def extract_fields_from_text(text: str) -> dict:
    """
    Use regex to find Invoice No., Amount, and Date from raw OCR text.
    Returns dict with keys: invoice_no, amount, date (None if not found).
    """
    # ── Invoice Number ──
    inv_patterns = [
        r"invoice\s*(?:no\.?|number|#)[:\s]*([A-Z0-9\-/]+)",
        r"inv\.?\s*(?:no\.?|#)[:\s]*([A-Z0-9\-/]+)",
        r"bill\s*(?:no\.?|number)[:\s]*([A-Z0-9\-/]+)",
        r"receipt\s*(?:no\.?|number)[:\s]*([A-Z0-9\-/]+)",
        r"#\s*([A-Z0-9\-]{4,})",
    ]
    invoice_no = None
    for pat in inv_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            invoice_no = m.group(1).strip()
            break

    # ── Amount ──
    amt_patterns = [
        r"(?:total|grand\s*total|amount\s*due|net\s*amount|balance\s*due)[:\s]*(?:rs\.?|inr|usd|\$|€|£)?[\s]*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"(?:rs\.?|inr|usd|\$|€|£)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        r"([0-9,]+\.[0-9]{2})\s*(?:only|/-)",
    ]
    amount = None
    for pat in amt_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            amount = m.group(1).replace(",", "").strip()
            break

    # ── Date ──
    date_patterns = [
        r"(?:invoice\s*date|date\s*of\s*invoice|date|bill\s*date)[:\s]*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})",
        r"(?:invoice\s*date|date\s*of\s*invoice|date|bill\s*date)[:\s]*(\d{1,2}\s+\w+\s+\d{4})",
        r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b",
        r"\b(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{4})\b",
    ]
    date = None
    for pat in date_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            date = m.group(1).strip()
            break

    return {"invoice_no": invoice_no, "amount": amount, "date": date}


def fields_complete(fields: dict) -> bool:
    return all(fields.get(k) for k in ["invoice_no", "amount", "date"])


# ─── CLAUDE VISION FALLBACK ───────────────────────────────────────────────────

def extract_via_claude(image_path: str) -> dict:
    """
    Send the original image to Claude Vision and ask it to extract fields.
    Returns dict with invoice_no, amount, date.
    """
    try:
        import anthropic
    except ImportError:
        print("[WARN] anthropic package not installed. Skipping Claude fallback.")
        print("       Run: pip install anthropic")
        return {}

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    # Read and base64-encode the image
    img_bytes = Path(image_path).read_bytes()
    b64_data = base64.standard_b64encode(img_bytes).decode("utf-8")

    # Determine media type
    suffix = Path(image_path).suffix.lower()
    media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".png": "image/png", ".webp": "image/webp",
                 ".gif": "image/gif"}
    media_type = media_map.get(suffix, "image/jpeg")

    prompt = """You are an invoice data extraction specialist.
Extract the following fields from this invoice image and return ONLY a valid JSON object:
{
  "invoice_no": "<invoice number or null>",
  "amount": "<total amount as numeric string, no currency symbol, or null>",
  "date": "<invoice date in DD/MM/YYYY or as written, or null>"
}
If a field is not found, set it to null. Return ONLY the JSON, no explanation."""

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)


# ─── MAIN PIPELINE ────────────────────────────────────────────────────────────

def extract_invoice_fields(image_path: str, verbose: bool = False) -> dict:
    """
    Full pipeline: preprocess → Tesseract → regex → Claude fallback.
    """
    print(f"\n📄 Processing: {image_path}")

    # Step 1: Preprocess
    print("  [1/3] Preprocessing image...")
    processed = preprocess_image(image_path)

    # Step 2: Tesseract OCR
    print("  [2/3] Running Tesseract OCR...")
    raw_text, confidence = run_tesseract(processed)

    if verbose:
        print(f"\n--- RAW OCR TEXT (confidence={confidence:.1f}%) ---")
        print(raw_text)
        print("---")

    # Step 3: Regex extraction
    fields = extract_fields_from_text(raw_text)
    print(f"       Tesseract confidence: {confidence:.1f}%")
    print(f"       Fields found by regex: {fields}")

    # Step 4: Claude fallback if confidence is low or fields missing
    if USE_CLAUDE_FALLBACK and (confidence < CONFIDENCE_THRESHOLD or not fields_complete(fields)):
        print("  [3/3] Low confidence or missing fields → using Claude Vision...")
        claude_fields = extract_via_claude(image_path)
        # Merge: prefer Claude result where regex failed
        for key in ["invoice_no", "amount", "date"]:
            if not fields.get(key) and claude_fields.get(key):
                fields[key] = claude_fields[key]
        print(f"       Claude Vision result: {claude_fields}")
    else:
        print("  [3/3] Tesseract result is reliable, skipping Claude fallback.")

    fields["source_file"] = Path(image_path).name
    fields["tesseract_confidence"] = round(confidence, 1)
    return fields


# ─── GUI ENTRY POINT ─────────────────────────────────────────────────────────

def pick_images() -> list[str]:
    """Open a file dialog and return selected image paths."""
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    root.attributes("-topmost", True)  # Bring dialog to front

    paths = filedialog.askopenfilenames(
        title="Select Invoice Image(s)",
        filetypes=[
            ("Image files", "*.jpg *.jpeg *.png *.webp *.gif *.bmp *.tiff"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()
    return list(paths)


def show_results_popup(results: list[dict]):
    """Show extracted results in a simple popup window."""
    root = tk.Tk()
    root.title("Invoice Extraction Results")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    tk.Label(root, text="Invoice Extraction Results",
             font=("Helvetica", 14, "bold"), pady=10).pack()

    for r in results:
        frame = tk.LabelFrame(root, text=r.get("source_file", ""),
                              padx=10, pady=8, font=("Helvetica", 10, "bold"))
        frame.pack(fill="x", padx=15, pady=6)

        fields = [
            ("Invoice No.", r.get("invoice_no") or "NOT FOUND"),
            ("Amount",      r.get("amount")     or "NOT FOUND"),
            ("Date",        r.get("date")        or "NOT FOUND"),
            ("Confidence",  f"{r.get('tesseract_confidence', 0)}%"),
        ]
        for label, value in fields:
            row = tk.Frame(frame)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{label}:", width=14, anchor="w",
                     font=("Helvetica", 10, "bold")).pack(side="left")
            tk.Label(row, text=value, anchor="w",
                     font=("Helvetica", 10)).pack(side="left")

    tk.Button(root, text="Close", command=root.destroy,
              width=12, pady=4).pack(pady=12)
    root.mainloop()


def main():
    global USE_CLAUDE_FALLBACK

    # ── Pick images via dialog ──
    image_paths = pick_images()
    if not image_paths:
        print("No images selected. Exiting.")
        sys.exit(0)

    results = []
    for path in image_paths:
        result = extract_invoice_fields(path, verbose=False)
        results.append(result)

        print("\n✅ EXTRACTED FIELDS:")
        print(f"   Invoice No. : {result.get('invoice_no') or 'NOT FOUND'}")
        print(f"   Amount      : {result.get('amount') or 'NOT FOUND'}")
        print(f"   Date        : {result.get('date') or 'NOT FOUND'}")
        print(f"   Confidence  : {result.get('tesseract_confidence')}%")

    # ── Show popup with results ──
    show_results_popup(results)

    # ── Optionally save JSON ──
    save = input("\n💾 Save results to JSON? (y/n): ").strip().lower()
    if save == "y":
        out_path = Path(image_paths[0]).parent / "invoice_results.json"
        with open(out_path, "w") as f:
            json.dump(results if len(results) > 1 else results[0], f, indent=2)
        print(f"   Saved to: {out_path}")

    return results


if __name__ == "__main__":
    main()