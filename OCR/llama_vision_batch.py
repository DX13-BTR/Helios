# llama_vision_batch.py
# Local Llama 3.2 Vision batch runner for Halifax statements → CSV
# - GPU pinned to device 0 (3060 Ti)
# - NDJSON per page (robust against truncation)
# - Balance-delta validator for Money In/Out correctness
# - Verbose progress + retries

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

# --------------------
# CONFIG
# --------------------
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")  # Pin to GPU 0 (your 3060 Ti)

MODEL = "llama3.2-vision"  # If you create a Modelfile, set MODEL = "llama3.2-vision-gpu"
DPI = 300                  # 280–320 is a good range; higher is slower but clearer
TIMEOUT = 180              # seconds per-page call to the model
OLLAMA_OPTS = [
    "-o", "num_gpu=99",        # offload as many layers as possible
    "-o", "temperature=0.1",   # stable decoding
    "-o", "num_ctx=8192",      # larger context for dense pages
]

# Poppler (pdftoppm) must be in PATH (you already set this up)
# Test in a terminal:  pdftoppm -v

PROMPT = """You are a precise bank statement extractor.
Return ONLY NDJSON (newline-delimited JSON). No prose. No arrays. No commas between objects.

For each transaction row on this page image, output ONE line containing a JSON object:
{"date":"DD Mon YY","description":"...","type":"...","money_in": number|null, "money_out": number|null, "balance": number}

Rules:
- One transaction per line (no surrounding brackets).
- Copy numbers exactly as shown. If a cell is blank, use null.
- Balance is the printed running balance at the row end (use leading minus if shown).
- Description includes the full merchant/payee text but excludes date/type/amount/balance.
- Absolutely NO text before/after the NDJSON.
"""

DATE_DD_MON_YY = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{2}$")
MONEY = re.compile(r"^-?\d+(?:,\d{3})*\.\d{2}$")


# --------------------
# Helpers
# --------------------
def run(cmd: List[str], input_bytes: Optional[bytes] = None, timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, input=input_bytes, capture_output=True, timeout=timeout)

def pdf_to_pngs(pdf_path: Path, out_dir: Path, dpi: int = DPI) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / pdf_path.stem
    cp = run(["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(base)], timeout=300)
    if cp.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {cp.stderr.decode(errors='ignore')}")
    pages = sorted(out_dir.glob(f"{pdf_path.stem}-*.png"),
                   key=lambda p: int(p.stem.split("-")[-1]))
    if not pages:
        raise RuntimeError("No PNG pages produced (pdftoppm).")
    return pages

def call_llama_vision(image_path: Path) -> List[Dict[str, Any]]:
    prompt = f"<image>{image_path.as_posix()}</image>\n{PROMPT}"
    cp = run(["ollama", "run", MODEL, *OLLAMA_OPTS],
             input_bytes=prompt.encode("utf-8"),
             timeout=TIMEOUT)
    if cp.returncode != 0:
        raise RuntimeError(f"Ollama error: {cp.stderr.decode(errors='ignore')}")
    # NDJSON: one JSON object per line
    lines = cp.stdout.decode("utf-8").splitlines()
    objs: List[Dict[str, Any]] = []
    for line in lines:
        s = line.strip()
        if not (s.startswith("{") and s.endswith("}")):
            continue
        try:
            objs.append(json.loads(s))
        except json.JSONDecodeError:
            s2 = s.rstrip(",\ufeff")
            try:
                objs.append(json.loads(s2))
            except Exception:
                # Skip malformed line; validator will keep us consistent
                pass
    return objs

def to_float(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("Â£", "").replace("£", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None

def norm_date_dd_mon_yy(s: str) -> Optional[str]:
    s = (s or "").strip()
    if not DATE_DD_MON_YY.match(s):
        return None
    try:
        return datetime.strptime(s, "%d %b %y").strftime("%Y-%m-%d")
    except Exception:
        return None

def validate_and_fix(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize fields and use balance-delta math to place Money In/Out correctly.
    Also flips sides if the running-balance check indicates a mismatch.
    """
    # Normalize
    for r in rows:
        r["date"] = r.get("date")
        r["description"] = (r.get("description") or "").strip()
        r["type"] = (r.get("type") or "").strip().upper()
        r["money_in"] = to_float(r.get("money_in"))
        r["money_out"] = to_float(r.get("money_out"))
        r["balance"] = to_float(r.get("balance"))

    # First pass: if both sides set or both None, use balance delta to choose
    prev_balance = None
    for r in rows:
        bal = r["balance"]
        v_in, v_out = r["money_in"], r["money_out"]

        if prev_balance is not None and bal is not None:
            # If both set or both None, decide by delta
            if (v_in is not None and v_out is not None) or (v_in is None and v_out is None):
                diff = round(bal - prev_balance, 2)
                if v_in is not None and v_out is not None:
                    # Keep the one that matches delta
                    if abs(diff - v_in) < 0.01 and abs(diff + v_out) >= 0.01:
                        r["money_out"] = None
                    elif abs(diff + v_out) < 0.01 and abs(diff - v_in) >= 0.01:
                        r["money_in"] = None
                    else:
                        # Prefer the one closer in magnitude to diff
                        if abs(abs(diff) - abs(v_in)) <= abs(abs(diff) - abs(v_out)):
                            r["money_out"] = None
                        else:
                            r["money_in"] = None
                else:
                    # None set → infer from diff
                    if abs(diff) > 0:
                        if diff > 0:
                            r["money_in"], r["money_out"] = abs(diff), None
                        else:
                            r["money_in"], r["money_out"] = None, abs(diff)
        prev_balance = bal if bal is not None else prev_balance

    # Second pass: compute amount and verify running balance; flip if needed
    prev_balance = None
    for r in rows:
        v_in, v_out, bal = r["money_in"], r["money_out"], r["balance"]
        r["amount"] = v_in if v_in is not None else (-v_out if v_out is not None else None)

        if prev_balance is not None and bal is not None and r["amount"] is not None:
            diff = round(bal - prev_balance, 2)
            if abs(diff - r["amount"]) > 0.01:
                # Flip side and recompute
                if v_in is not None and v_out is None:
                    r["money_in"], r["money_out"] = None, abs(v_in)
                elif v_out is not None and v_in is None:
                    r["money_in"], r["money_out"] = abs(v_out), None
                r["amount"] = r["money_in"] if r["money_in"] is not None else (
                    -r["money_out"] if r["money_out"] is not None else None
                )

        prev_balance = bal if bal is not None else prev_balance

    return rows


# --------------------
# Main per-PDF pipeline
# --------------------
def process_pdf(pdf_path: Path, output_dir: Path):
    print(f"\nProcessing {pdf_path.name} ...")
    t0 = time.time()

    with tempfile.TemporaryDirectory() as tmpd:
        tmp = Path(tmpd)
        page_dir = tmp / "pages"
        print("  1/3 Rendering pages with pdftoppm ...")
        pages = pdf_to_pngs(pdf_path, page_dir, dpi=DPI)
        print(f"     -> {len(pages)} pages")

        all_rows: List[Dict[str, Any]] = []
        for idx, p in enumerate(pages, start=1):
            pstart = time.time()
            print(f"  2/3 Page {idx}/{len(pages)} → Llama …")
            data: Optional[List[Dict[str, Any]]] = None
            for attempt in range(1, 4):  # up to 3 tries
                try:
                    data = call_llama_vision(p)
                    break
                except Exception as e:
                    print(f"     attempt {attempt}/3 failed: {e}")
                    time.sleep(2)
            if data is None:
                print("     giving up on this page (no data).")
                continue

            fixed = validate_and_fix(data)
            all_rows.extend(fixed)
            print(f"     page done in {time.time() - pstart:.1f}s, rows: {len(fixed)}")

    df = pd.DataFrame(all_rows)

    # Normalize date to ISO for output and enforce column ordering
    def to_iso(s):
        try:
            return datetime.strptime(str(s), "%d %b %y").strftime("%Y-%m-%d")
        except Exception:
            return s

    if not df.empty:
        if "date" in df.columns:
            df["date"] = df["date"].apply(to_iso)
        columns = ["date", "description", "type", "amount", "money_in", "money_out", "balance"]
        for c in columns:
            if c not in df.columns:
                df[c] = None
        df = df[columns]

    out = output_dir / f"{pdf_path.stem}.csv"
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"  3/3 Wrote {len(df)} rows → {out} in {time.time() - t0:.1f}s")
    return out, len(df)


# --------------------
# CLI
# --------------------
def main():
    parser = argparse.ArgumentParser(description="Local Llama Vision: Halifax PDFs → CSVs")
    parser.add_argument("input", help="Folder with PDF statements")
    parser.add_argument("output", help="Folder for CSV output")
    parser.add_argument("--merge", action="store_true", help="Also write merged CSV across all PDFs")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    totals = []
    for pdf in sorted(input_dir.glob("*.pdf")):
        try:
            path, n = process_pdf(pdf, output_dir)
            totals.append((pdf.name, n))
        except Exception as e:
            print(f" !! {pdf.name}: {e}")
            totals.append((pdf.name, 0))

    if args.merge:
        merged_frames = []
        for csvf in sorted(output_dir.glob("*.csv")):
            try:
                df = pd.read_csv(csvf)
                df["source"] = csvf.stem
                merged_frames.append(df)
            except Exception:
                pass
        if merged_frames:
            merged = pd.concat(merged_frames, ignore_index=True)
            merged.to_csv(output_dir / "merged_all.csv", index=False, encoding="utf-8")
            print(f" -> merged_all.csv saved with {len(merged)} rows")


if __name__ == "__main__":
    main()
