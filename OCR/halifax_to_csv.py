import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytesseract
from pdf2image import convert_from_path

# If Tesseract is not on PATH, uncomment and point to it:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# If Poppler is not on PATH, set folder with pdftoppm.exe / pdfinfo.exe:
POPPLER_BIN = None  # e.g. r"C:\Poppler\poppler-24.08.0\Library\bin"

def ocr_pdf_to_lines(pdf_path: Path, dpi: int = 200) -> pd.DataFrame:
    """Convert a PDF to OCR lines (page,text)."""
    images = convert_from_path(str(pdf_path), dpi=dpi, poppler_path=POPPLER_BIN)
    rows = []
    for page_num, image in enumerate(images, start=1):
        text = pytesseract.image_to_string(image)
        for line in text.splitlines():
            line = line.strip()
            if line:
                rows.append({"page": page_num, "text": line})
    return pd.DataFrame(rows)

def parse_halifax_transactions(ocr_df: pd.DataFrame) -> pd.DataFrame:
    """Parse Halifax OCR output into structured transactions using balance delta."""
    txn_pattern = re.compile(r"^\d{2} \w{3} \d{2}")
    money_token = re.compile(r"-?\d+\.\d{2}")

    transactions = []
    prev_balance = None

    for _, row in ocr_df.iterrows():
        text = str(row["text"])
        if not txn_pattern.match(text):
            continue

        parts = text.split()

        # Date
        date_str = " ".join(parts[0:3])
        try:
            date_iso = datetime.strptime(date_str, "%d %b %y").strftime("%Y-%m-%d")
        except ValueError:
            continue

        # First money token index (start of numeric tail)
        money_idxs = [i for i, p in enumerate(parts) if money_token.match(p)]
        if not money_idxs:
            continue

        first_money_idx = money_idxs[0]
        if first_money_idx < 4:  # not enough room for desc + type
            continue

        desc_parts = parts[3:first_money_idx - 1]
        txn_type = parts[first_money_idx - 1]
        nums_after_type = parts[first_money_idx:]

        money_in = None
        money_out = None
        balance = None

        try:
            if len(nums_after_type) == 3:
                # money_in, money_out, balance
                money_in = float(nums_after_type[0])
                money_out = float(nums_after_type[1])
                balance = float(nums_after_type[2])
            elif len(nums_after_type) == 2:
                # single amount + balance; use balance delta instead of type guess
                val1 = float(nums_after_type[0])
                balance = float(nums_after_type[1])

                if prev_balance is not None:
                    diff = round(balance - prev_balance, 2)
                    if abs(diff - val1) < 0.01:
                        money_in = val1
                    elif abs(diff + val1) < 0.01:
                        money_out = val1
                    else:
                        # fallback to type heuristic only if math is inconclusive
                        if txn_type in ("FPI", "TFR", "CR"):
                            money_in = val1
                        else:
                            money_out = val1
                else:
                    # first row in the file; no previous balance to compare
                    if txn_type in ("FPI", "TFR", "CR"):
                        money_in = val1
                    else:
                        money_out = val1
            else:
                # Unexpected layout; skip
                continue
        except ValueError:
            continue

        amount = money_in if money_in is not None else (-money_out if money_out is not None else None)
        prev_balance = balance if balance is not None else prev_balance

        transactions.append({
            "date": date_iso,
            "description": " ".join(desc_parts),
            "type": txn_type,
            "amount": amount,
            "money_in": money_in,
            "money_out": money_out,
            "balance": balance,
        })

    return pd.DataFrame(transactions)

def process_statement(pdf_path: Path, output_csv: Path):
    print(f"OCR processing: {pdf_path.name}")
    ocr_df = ocr_pdf_to_lines(pdf_path)
    parsed_df = parse_halifax_transactions(ocr_df)
    parsed_df.to_csv(output_csv, index=False, encoding="utf-8")
    print(f"✅ Saved {len(parsed_df)} transactions to {output_csv}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Halifax PDF statement to CSV via OCR")
    parser.add_argument("pdf", type=str, help="Path to Halifax PDF")
    parser.add_argument("--output", type=str, help="Path to output CSV (default: same name as PDF)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    output_csv = Path(args.output) if args.output else pdf_path.with_suffix(".csv")
    process_statement(pdf_path, output_csv)
