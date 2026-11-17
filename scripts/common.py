"""Shared helpers for multi-xlsx ranking scripts (Economatica & standard Excel compatible)."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Iterable

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.data_loader import EbitdaMode, default_data_manager  # noqa: E402


def equal_weight(n: int) -> float:
    if n <= 0:
        raise ValueError("Portfolio size must be positive")
    return 1.0 / n


def _parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def _resolve_cli_data_dir(explicit: Path | None, default_data_dir: str) -> Path:
    if explicit is not None:
        return explicit
    for cand in (Path(default_data_dir), Path("./data"), Path("./dados")):
        if cand.is_dir() and any(cand.glob("*.xlsx")):
            return cand
    candidate = Path(default_data_dir)
    if candidate.is_dir():
        return candidate
    return Path(input(f"Data directory [{default_data_dir}]: ").strip() or default_data_dir)


def parse_args_or_prompt(
    description: str,
    default_data_dir: str = "./dados",
) -> tuple[Path, date, int, bool]:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=f"Directory with one .xlsx per asset (default: ./data or {default_data_dir})",
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
    parser.add_argument(
        "--allow-duplicate-issuers",
        action="store_true",
        help="Allow multiple share classes (ON/PN/UNIT) of the same company in the portfolio",
    )
    args = parser.parse_args()

    data_dir = _resolve_cli_data_dir(args.data_dir, default_data_dir)
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

    deduplicate_issuers = not args.allow_duplicate_issuers
    return data_dir, as_of, n, deduplicate_issuers


def load_universe(
    data_dir: Path | str,
    as_of: date | str,
    *,
    require_roic: bool = False,
    ebitda_mode: EbitdaMode = "ltm",
    deduplicate_issuers: bool = False,
) -> pd.DataFrame:
    """Load valid asset universe as of ``as_of`` from ``data_dir``."""
    folder = Path(data_dir)
    paths = sorted(p for p in folder.glob("*.xlsx") if not p.name.startswith("~$"))
    if not paths:
        raise FileNotFoundError(f"No .xlsx files found in {folder}")

    as_of_date = _parse_date(as_of)
    dataset = default_data_manager.load(folder)
    snap = dataset.snapshot_fundamentals(as_of_date, ebitda_mode=ebitda_mode)
    if snap.empty:
        raise ValueError(f"No valid assets found for {as_of_date.isoformat()} in {folder}")

    mask = np.isfinite(snap["EV"].to_numpy(dtype=np.float64)) & (snap["EV"].to_numpy(dtype=np.float64) > 0.0)
    mask &= np.isfinite(snap["EBITDA"].to_numpy(dtype=np.float64))
    if require_roic:
        mask &= np.isfinite(snap["ROIC"].to_numpy(dtype=np.float64))

    valid_df = snap.loc[mask].copy()
    if valid_df.empty:
        raise ValueError(f"No valid assets found for {as_of_date.isoformat()} in {folder}")

    if deduplicate_issuers and "issuer" in valid_df.columns:
        valid_df["_ey"] = valid_df["EBITDA"] / valid_df["EV"]
        valid_df = (
            valid_df.sort_values(["presence_63d", "_ey", "ativo"], ascending=[False, False, True])
            .drop_duplicates(subset=["issuer"], keep="first")
            .drop(columns=["_ey"])
            .copy()
        )

    return valid_df.reset_index(drop=True)


def to_portfolio(
    ranked: Iterable[tuple[str, float]],
    n: int,
) -> list[tuple[str, float, float]]:
    selected = list(ranked)[:n]
    if not selected:
        return []
    weight = equal_weight(len(selected))
    return [(name, score, weight) for name, score in selected]
