"""Shared helpers for multi-xlsx ranking scripts."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

DATE_ALIASES = {"date", "data"}
COLUMN_ALIASES = {
    "ebitda": "EBITDA",
    "ev": "EV",
    "roic": "ROIC",
    "close": "Close",
    "preco": "Close",
    "preço": "Close",
    "adj close": "Close",
    "adj_close": "Close",
    "adjclose": "Close",
}


def equal_weight(n: int) -> float:
    if n <= 0:
        raise ValueError("Portfolio size must be positive")
    return 1.0 / n


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in DATE_ALIASES:
            rename[col] = "Date"
        elif key in COLUMN_ALIASES:
            rename[col] = COLUMN_ALIASES[key]
    return df.rename(columns=rename)


def _parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def parse_args_or_prompt(
    description: str,
    default_data_dir: str = "./dados",
) -> tuple[Path, date, int]:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=f"Directory with one .xlsx per asset (default: {default_data_dir})",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="Number of stocks in the portfolio",
    )
    args = parser.parse_args()

    data_dir = args.data_dir
    if data_dir is None:
        candidate = Path(default_data_dir)
        if candidate.is_dir():
            data_dir = candidate
        else:
            data_dir = Path(input(f"Data directory [{default_data_dir}]: ").strip() or default_data_dir)

    if not data_dir.is_dir():
        raise SystemExit(f"Data directory not found: {data_dir}")

    if args.date is None:
        raw_date = input("Date (YYYY-MM-DD): ").strip()
    else:
        raw_date = args.date
    as_of = _parse_date(raw_date)

    if args.n is None:
        raw_n = input("Portfolio size (n): ").strip()
        n = int(raw_n)
    else:
        n = args.n

    if n <= 0:
        raise SystemExit("Portfolio size --n must be a positive integer")

    return data_dir, as_of, n


def _row_for_date(df: pd.DataFrame, as_of: date) -> pd.Series | None:
    if "Date" not in df.columns:
        return None

    dates = pd.to_datetime(df["Date"], errors="coerce").dt.date
    matched = df.loc[dates == as_of]
    if matched.empty:
        return None
    return matched.iloc[-1]


def load_universe(
    data_dir: Path,
    as_of: date,
    *,
    require_roic: bool = False,
) -> pd.DataFrame:
    """Load one row per asset for ``as_of`` from each ``*.xlsx`` in ``data_dir``."""
    paths = sorted(data_dir.glob("*.xlsx"))
    if not paths:
        raise FileNotFoundError(f"No .xlsx files found in {data_dir}")

    required = ["EBITDA", "EV"]
    if require_roic:
        required.append("ROIC")

    rows: list[dict[str, object]] = []
    for path in paths:
        asset = path.stem
        try:
            raw = pd.read_excel(path, engine="openpyxl")
        except Exception as exc:  # noqa: BLE001 - surface file-level failures
            print(f"Warning: failed to read {path.name}: {exc}", file=sys.stderr)
            continue

        df = _normalize_columns(raw)
        missing = [c for c in ["Date", *required] if c not in df.columns]
        if missing:
            print(
                f"Warning: {path.name} missing columns {missing}; skipped",
                file=sys.stderr,
            )
            continue

        row = _row_for_date(df, as_of)
        if row is None:
            print(f"Warning: {asset} has no row for {as_of.isoformat()}; skipped", file=sys.stderr)
            continue

        record: dict[str, object] = {"ativo": asset}
        valid = True
        for col in required:
            value = pd.to_numeric(row[col], errors="coerce")
            if pd.isna(value):
                print(f"Warning: {asset} has invalid {col} on {as_of.isoformat()}; skipped", file=sys.stderr)
                valid = False
                break
            record[col] = float(value)

        if not valid:
            continue

        if float(record["EV"]) <= 0:
            print(f"Warning: {asset} has EV <= 0 on {as_of.isoformat()}; skipped", file=sys.stderr)
            continue

        rows.append(record)

    if not rows:
        raise ValueError(f"No valid assets found for {as_of.isoformat()} in {data_dir}")

    return pd.DataFrame(rows)


def to_portfolio(
    ranked: Iterable[tuple[str, float]],
    n: int,
) -> list[tuple[str, float, float]]:
    selected = list(ranked)[:n]
    if not selected:
        return []
    weight = equal_weight(len(selected))
    return [(name, score, weight) for name, score in selected]


def load_panel(data_dir: Path, *, require_roic: bool = False) -> pd.DataFrame:
    """Load all ``*.xlsx`` files into a long panel (one row per asset-date)."""
    paths = sorted(data_dir.glob("*.xlsx"))
    if not paths:
        raise FileNotFoundError(f"No .xlsx files found in {data_dir}")

    required = ["EBITDA", "EV"]
    if require_roic:
        required.append("ROIC")

    frames: list[pd.DataFrame] = []
    for path in paths:
        try:
            raw = pd.read_excel(path, engine="openpyxl")
        except Exception as exc:  # noqa: BLE001 - surface file-level failures
            print(f"Warning: failed to read {path.name}: {exc}", file=sys.stderr)
            continue

        df = _normalize_columns(raw)
        missing = [c for c in ["Date", *required] if c not in df.columns]
        if missing:
            print(f"Warning: {path.name} missing columns {missing}; skipped", file=sys.stderr)
            continue

        df = df.copy()
        df["ativo"] = path.stem
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
        df["EBITDA"] = pd.to_numeric(df["EBITDA"], errors="coerce")
        df["EV"] = pd.to_numeric(df["EV"], errors="coerce")
        if "ROIC" in df.columns:
            df["ROIC"] = pd.to_numeric(df["ROIC"], errors="coerce")
        if "Close" in df.columns:
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce")

        df = df.dropna(subset=["Date", *required])
        df = df.loc[df["EV"] > 0]
        if df.empty:
            print(f"Warning: {path.name} has no valid rows; skipped", file=sys.stderr)
            continue
        frames.append(df)

    if not frames:
        raise ValueError(f"No valid asset rows found in {data_dir}")

    return pd.concat(frames, ignore_index=True)


def universe_as_of(
    panel: pd.DataFrame,
    as_of: date,
    *,
    require_roic: bool = False,
    max_age_days: int | None = None,
) -> pd.DataFrame:
    """Last valid observation per asset with ``Date <= as_of``."""
    eligible = panel.loc[panel["Date"] <= as_of].copy()
    if eligible.empty:
        raise ValueError(f"No observations on or before {as_of.isoformat()}")

    eligible = eligible.sort_values(["ativo", "Date"])
    latest = eligible.groupby("ativo", as_index=False).tail(1)

    if max_age_days is not None:
        latest = latest.loc[latest["Date"].map(lambda d: (as_of - d).days <= max_age_days)]

    required = ["EBITDA", "EV"]
    if require_roic:
        required.append("ROIC")
        latest = latest.dropna(subset=["ROIC"])

    latest = latest.dropna(subset=required)
    latest = latest.loc[latest["EV"] > 0]
    if latest.empty:
        raise ValueError(f"No valid assets found for {as_of.isoformat()}")
    return latest.reset_index(drop=True)


def rebalance_dates(start: date, end: date, freq: str) -> list[date]:
    """Calendar period-ends between ``start`` and ``end`` (inclusive)."""
    if end < start:
        raise ValueError("end date must be on or after start date")

    aliases = {
        "M": ("ME", "M"),
        "Q": ("QE", "Q"),
        "Y": ("YE", "A"),
    }
    if freq not in aliases:
        raise ValueError(f"Unsupported frequency: {freq}")

    primary, fallback = aliases[freq]
    try:
        idx = pd.date_range(start, end, freq=primary)
    except ValueError:
        idx = pd.date_range(start, end, freq=fallback)
    return [ts.date() for ts in idx]


def price_as_of(panel: pd.DataFrame, asset: str, as_of: date) -> float | None:
    if "Close" not in panel.columns:
        return None
    rows = panel.loc[(panel["ativo"] == asset) & (panel["Date"] <= as_of) & panel["Close"].notna()]
    if rows.empty:
        return None
    price = float(rows.sort_values("Date").iloc[-1]["Close"])
    if price <= 0 or pd.isna(price):
        return None
    return price


def holding_period_return(
    panel: pd.DataFrame,
    holdings: list[tuple[str, float, float]],
    start: date,
    end: date,
) -> float | None:
    """Equal-weight (renormalized) return from ``start`` to ``end`` using Close."""
    pairs: list[tuple[float, float]] = []
    for name, _nota, weight in holdings:
        p0 = price_as_of(panel, name, start)
        p1 = price_as_of(panel, name, end)
        if p0 is None or p1 is None:
            continue
        pairs.append((weight, p1 / p0 - 1.0))
    if not pairs:
        return None
    weight_sum = sum(weight for weight, _ret in pairs)
    if weight_sum <= 0:
        return None
    return sum((weight / weight_sum) * ret for weight, ret in pairs)


def turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    names = set(previous) | set(current)
    if not names:
        return 0.0
    return 0.5 * sum(abs(current.get(name, 0.0) - previous.get(name, 0.0)) for name in names)
