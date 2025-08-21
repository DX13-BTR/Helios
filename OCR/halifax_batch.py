import re
from pathlib import Path
from datetime import datetime
import pandas as pd
import pytesseract
from pdf2image import convert_from_path

# --- CONFIG ---
POPPLER_BIN = None  # e.g. r"C:\Poppler\poppler-24.08.0\Library\bin"
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

DATE_LINE = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{2}\b")
MONEY = re.compile(r"^-?\d+(?:,\d{3})*\.\d{2}$")

def to_float(s: str | None):
    if not s:
        return None
    s = s.replace("Â£", "").replace("£", "").replace(",", "").strip()
    try:
        return float(s)
    except:
        return None

def ocr_pdf(pdf_path: Path, dpi: int = 220) -> list[tuple[int, str]]:
    images = convert_from_path(str(pdf_path), dpi=dpi, poppler_path=POPPLER_BIN)
    lines = []
    for pno, img in enumerate(images, start=1):
        text = pytesseract.image_to_string(img)
        for line in text.splitlines():
            if line.strip():
                lines.append((pno, line.strip()))
    return lines

def parse_transactions(lines: list[tuple[int, str]]):
    txns = []
    prev_balance = None

    for _, line in lines:
        if not DATE_LINE.match(line):
            continue
        parts = line.split()
        date_str = " ".join(parts[:3])
        try:
            date_iso = datetime.strptime(date_str, "%d %b %y").strftime("%Y-%m-%d")
        except:
            continue

        # Find money fields
        money_idxs = [i for i, p in enumerate(parts) if MONEY.match(p)]
        if not money_idxs:
            continue

        desc_parts = parts[3:money_idxs[0]-1]
        txn_type = parts[money_idxs[0]-1]
        nums = [to_float(parts[i]) for i in money_idxs]

        money_in, money_out, balance = None, None, None
        if len(nums) == 3:
            money_in, money_out, balance = nums
        elif len(nums) == 2:
            amount, balance = nums
            if prev_balance is not None:
                diff = round(balance - prev_balance, 2)
                if abs(diff - amount) < 0.01:
                    money_in = amount
                elif abs(diff + amount) < 0.01:
                    money_out = amount
                else:
                    if txn_type in ('FPI', 'TFR', 'CR'):
                        money_in = amount
                    else:
                        money_out = amount
            else:
                if txn_type in ('FPI', 'TFR', 'CR'):
                    money_in = amount
                else:
                    money_out = amount
        prev_balance = balance

        txns.append({
            "date": date_iso,
            "description": " ".join(desc_parts),
            "type": txn_type,
            "amount": money_in if money_in is not None else -money_out,
            "money_in": money_in,
            "money_out": money_out,
            "balance": balance
        })

    return txns

def process_folder(input_dir: Path, output_dir: Path):
    output_dir.mkdir(exist_ok=True)
    for pdf_file in input_dir.glob("*.pdf"):
        print(f"Processing {pdf_file.name}...")
        lines = ocr_pdf(pdf_file)
        txns = parse_transactions(lines)
        df = pd.DataFrame(txns)
        out_path = output_dir / (pdf_file.stem + ".csv")
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} rows to {out_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Batch Halifax PDF -> CSV")
    parser.add_argument("input", help="Folder with PDF statements")
    parser.add_argument("output", help="Folder for CSV output")
    args = parser.parse_args()

    process_folder(Path(args.input), Path(args.output))
