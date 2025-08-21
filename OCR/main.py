import argparse
from pathlib import Path
import pandas as pd
from parser import extract_from_pdf
from utils import clean_dataframe, categorize_transactions

def main(input_dir, output_dir, categorize=False):
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_transactions = []

    for pdf_file in input_path.glob("*.pdf"):
        print(f"Processing: {pdf_file.name}")
        rows = extract_from_pdf(pdf_file)
        print(f" → {len(rows)} rows extracted")
        if not rows:
            print(f" ⚠️ No valid transactions in {pdf_file.name}")
        all_transactions.extend(rows)

    print(f"\nTotal transactions extracted: {len(all_transactions)}")

    headers = ["Date", "Description", "Type", "Money In", "Money Out", "Balance"]
    df = pd.DataFrame(all_transactions, columns=headers)
    df = clean_dataframe(df)

    if categorize:
        df = categorize_transactions(df)

    output_file = output_path / "halifax_combined.csv"
    df.to_csv(output_file, index=False)
    print(f"\n✅ Parsing complete. Output saved to: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse Halifax PDF statements to CSV")
    parser.add_argument("input_dir", help="Directory containing Halifax PDF statements")
    parser.add_argument("output_dir", help="Directory to write CSV output")
    parser.add_argument("--categorize", action="store_true", help="Categorize transactions")
    args = parser.parse_args()

    main(args.input_dir, args.output_dir, categorize=args.categorize)
