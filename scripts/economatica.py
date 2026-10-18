"""Read Economatica Excel exports in memory without rewriting dados/."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATE_ALIASES = {"data", "date"}


def _header_row_index(raw: pd.DataFrame) -> int:
    if raw.empty:
        raise ValueError("empty spreadsheet")
    first_col = raw.iloc[:, 0]
    for idx, value in enumerate(first_col):
        if pd.isna(value):
            continue
        if str(value).strip().lower() in DATE_ALIASES:
            return idx
    raise ValueError("no Data/Date header row found")


def _column_key(label: object) -> str:
    return str(label).split("\n", 1)[0].strip().lower()


def canonical_column_name(label: object) -> str | None:
    """Map the first line of an Economatica label to a canonical column name."""
    key = _column_key(label)
    if key in DATE_ALIASES:
        return "Date"
    if "ebitda" in key:
        return "EBITDA"
    if key.startswith("roic"):
        return "ROIC"
    if key.startswith("ev"):
        return "EV"
    return None


def map_economatica_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict[object, str] = {}
    for col in df.columns:
        canonical = canonical_column_name(col)
        if canonical is not None:
            rename[col] = canonical
    return df.rename(columns=rename)


def read_economatica_xlsx(path: Path | str) -> pd.DataFrame:
    """Load one Economatica ``.xlsx`` and map columns in memory.

    Finds the first row whose column A is ``Data`` or ``Date``, uses that row
    as headers, maps known prefixes (``EBITDA``, ``EV``, ``ROIC``) to canonical
    names, and replaces Economatica's ``-`` placeholders with NaN. The file on
    disk is never written.
    """
    path = Path(path)
    raw = pd.read_excel(path, header=None, engine="openpyxl")
    header_idx = _header_row_index(raw)
    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = raw.iloc[header_idx]
    data = data.replace("-", pd.NA)
    return map_economatica_columns(data).reset_index(drop=True)
