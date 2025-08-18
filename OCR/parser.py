import pdfplumber
import re

def extract_from_pdf(pdf_path):
    transactions = []
    date_pattern = re.compile(r"^\d{2} \w{3} \d{2}")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            print(f"\n📄 {pdf_path.name} — Page {page.page_number}")
            print("────────────────────────────────────────────")
            print(text if text else "[NO TEXT EXTRACTED]")
            if not text:
                continue

            lines = text.split("\n")
            for line in lines:
                line = line.strip()
                if date_pattern.match(line):
                    # Split on 2+ spaces to isolate fields
                    parts = re.split(r"\s{2,}", line)

                    if len(parts) < 5:
                        continue  # skip malformed lines

                    # Assign parts from left to right
                    date = parts[0]
                    description = parts[1]
                    tx_type = parts[2]

                    money_in, money_out = "", ""
                    if len(parts) == 6:
                        money_in = parts[3]
                        money_out = parts[4]
                        balance = parts[5]
                    elif len(parts) == 5:
                        # Infer direction
                        if tx_type in ["FPI", "BGC", "CR", "Faster Payment"] or "CR" in tx_type:
                            money_in = parts[3]
                        else:
                            money_out = parts[3]
                        balance = parts[4]
                    else:
                        continue  # skip if unknown structure

                    transactions.append({
                        "Date": date,
                        "Description": description,
                        "Type": tx_type,
                        "Money In": money_in,
                        "Money Out": money_out,
                        "Balance": balance,
                    })

    return transactions
