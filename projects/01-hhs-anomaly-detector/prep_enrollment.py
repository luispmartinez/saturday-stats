"""
prep_enrollment.py
------------------
Turns the three raw HHSC Excel files (title row + two-level headers + footnotes)
into clean flat CSVs that scan_and_profile.py can profile.

Reads from raw/, writes to drop/. Raw files are never modified.

Usage (from the project folder, venv active):
    python prep_enrollment.py
"""
import re
from pathlib import Path

import pandas as pd
import openpyxl
from datetime import datetime

def incomplete_months(xlsx_path):
    ws = openpyxl.load_workbook(xlsx_path).active
    flagged = {}
    for row in ws.iter_rows(min_row=1, max_col=1):
        cell = row[0]
        if isinstance(cell.value, datetime):                       # what does a data row hold in column A?
            flagged[cell.value] = cell.fill.fill_type == "solid"   # which fill type means highlighted?
    return flagged

HERE = Path(__file__).parent
RAW = HERE / "raw"
DROP = HERE / "drop"

JOBS = [
    # (raw file, output name, kind, period label)
    ("monthly-enrollment-by-risk-group.xlsx", "hhs_monthly_caseload.csv", "monthly", "monthly"),
    ("enrollment-by-county-prelim.xlsx", "hhs_county_prelim_may2026.csv", "county", "May 2026 (preliminary)"),
    ("enrollment-by-county-final-sfy25.xlsx", "hhs_county_final_sfy25.csv", "county", "SFY 2025 (final)"),
]


def slug(text: str) -> str:
    text = re.sub(r"[*]+", "", str(text))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    return text


def is_data_row(value, kind) -> bool:
    if pd.isna(value):
        return False
    if kind == "monthly":
        return isinstance(value, (pd.Timestamp,)) or hasattr(value, "year")
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def clean(path: Path, kind: str, period: str) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None)
    first = raw.iloc[:, 0]

    data_start = next((i for i, v in enumerate(first) if is_data_row(v, kind)), None)
    if data_start is None:
        raise ValueError(f"{path.name}: could not find the first data row")

    # Header block = non-empty rows above the data, minus the one-cell title row.
    header_rows = []
    for i in range(data_start):
        row = raw.iloc[i]
        if row.notna().sum() <= 1 and i == 0:
            continue  # title row
        if row.notna().any():
            header_rows.append(i)

    ncols = raw.shape[1]
    parts = []
    for i in header_rows:
        row = raw.iloc[i].copy()
        if row.notna().sum() <= ncols * 0.6:   # sparse "group" row: carry labels rightwards
            row = row.ffill()
        parts.append(row.astype(object))

    names = []
    for j in range(ncols):
        seen = []
        for row in parts:
            val = row.iloc[j]
            if pd.notna(val) and str(val).strip() and str(val).strip() not in seen:
                seen.append(str(val).strip())
        names.append(slug("__".join(seen)) or f"col_{j}")

    # Make names unique
    counts = {}
    uniq = []
    for n in names:
        counts[n] = counts.get(n, 0) + 1
        uniq.append(n if counts[n] == 1 else f"{n}_{counts[n]}")

    # Data rows run until the first non-data row (footnotes start there)
    end = data_start
    while end < len(raw) and is_data_row(raw.iloc[end, 0], kind):
        end += 1
    df = raw.iloc[data_start:end].copy()
    df.columns = uniq

    keep_text = {df.columns[0]} | ({df.columns[1]} if kind == "county" else set())
    for c in df.columns:
        if c not in keep_text:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if kind == "monthly":
        df = df.rename(columns={df.columns[0]: "month"})
        df["month"] = pd.to_datetime(df["month"]).dt.date
        df = df.sort_values("month").reset_index(drop=True)
    else:
        df = df.rename(columns={df.columns[0]: "county_code", df.columns[1]: "county"})
        df["county_code"] = pd.to_numeric(df["county_code"], errors="coerce").astype("Int64")
        df["period"] = period
    return df

def main() -> None:
    DROP.mkdir(exist_ok=True)
    for raw_name, out_name, kind, period in JOBS:
        src = RAW / raw_name
        if not src.exists():
            print(f"SKIP {raw_name}: not found in {RAW}")
            continue
        df = clean(src, kind, period)
        if kind == "monthly":
                flagged = incomplete_months(src)       # catch the returned dictionary here
                df["hhs_incomplete"] = pd.to_datetime(df["month"]).map(flagged)         # look each month up in flagged, map each month through flagged
                assert df["hhs_incomplete"].notna().all(), "some months had no match in the sheet"
                print(df.loc[df["hhs_incomplete"], "month"].astype(str).tolist())
                if df["hhs_incomplete"].any():
                    first_highlighted = df.loc[df["hhs_incomplete"], "month"].min()
                    last_unhighlighted = df.loc[~df["hhs_incomplete"], "month"].max()
                    print(type(first_highlighted), type(last_unhighlighted))
                    assert first_highlighted > last_unhighlighted, f"{first_highlighted:%b %Y} comes before {last_unhighlighted:%b %Y}"
        out = DROP / out_name
        df.to_csv(out, index=False)
        print(f"\n{raw_name} -> {out.name}  ({len(df)} rows x {df.shape[1]} cols)")
        print("  columns:", ", ".join(df.columns))
        print(df.head(3).to_string(index=False))


if __name__ == "__main__":
    main()
