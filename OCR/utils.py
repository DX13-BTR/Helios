# utils.py
import pandas as pd
import re

def clean_dataframe(df):
    df["Date"] = pd.to_datetime(df["Date"], format="%d %b %y")
    for col in ["Money In", "Money Out", "Balance"]:
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df = df.sort_values("Date")
    return df

def categorize_transactions(df):
    def tag(desc):
        d = desc.lower()
        if "mcdonalds" in d or "kfc" in d or "greggs" in d:
            return "Food"
        if "shell" in d or "bp" in d or "texaco" in d:
            return "Fuel"
        if "interest" in d or "od" in d:
            return "Fees"
        if "tfr" in d or "fpi" in d:
            return "Transfer"
        if "sainsburys" in d or "tesco" in d or "morrisons" in d:
            return "Groceries"
        return "Uncategorized"

    df["Category"] = df["Description"].apply(tag)
    return df