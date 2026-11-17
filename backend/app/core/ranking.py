"""Portfolio ranking logic for The Acquirer's Multiple and The Magic Formula."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from backend.app.core.data_loader import EbitdaMode, MarketDataset

StrategyName = Literal["acquirers_multiple", "magic_formula"]


@dataclass(slots=True)
class RankedHolding:
    ticker: str
    company_name: str
    issuer: str
    weight: float
    score: float  # 'nota': EBITDA/EV for Acquirer's, combined rank for Magic Formula
    earnings_yield: float
    roic: float | None
    ev: float
    ebitda: float
    price: float | None
    rank_yield: float | None = None
    rank_roic: float | None = None


def _filter_and_deduplicate(
    snapshot: pd.DataFrame,
    *,
    require_roic: bool,
    require_valid_price: bool,
    require_positive_ebitda: bool,
    deduplicate_issuers: bool,
    min_presence_63d: int,
) -> pd.DataFrame:
    if snapshot.empty:
        return snapshot

    df = snapshot.copy()

    mask = np.isfinite(df["EV"].to_numpy(dtype=np.float64)) & (df["EV"].to_numpy(dtype=np.float64) > 0.0)
    eb_arr = df["EBITDA"].to_numpy(dtype=np.float64)
    mask &= np.isfinite(eb_arr)
    if require_positive_ebitda:
        mask &= eb_arr > 0.0

    if require_roic:
        roic_arr = df["ROIC"].to_numpy(dtype=np.float64)
        mask &= np.isfinite(roic_arr)

    if require_valid_price:
        pr_arr = df["Price"].to_numpy(dtype=np.float64)
        mask &= np.isfinite(pr_arr) & (pr_arr > 0.0)
        if min_presence_63d > 0 and "presence_63d" in df.columns:
            mask &= df["presence_63d"].to_numpy(dtype=np.int32) >= min_presence_63d

    df = df.loc[mask].copy()
    if df.empty:
        return df

    df["earnings_yield"] = df["EBITDA"] / df["EV"]

    if deduplicate_issuers and "issuer" in df.columns:
        pres_col = "presence_63d" if "presence_63d" in df.columns else None
        sort_cols = ([pres_col] if pres_col else []) + ["earnings_yield", "ativo"]
        sort_asc = ([False] if pres_col else []) + [False, True]
        df = (
            df.sort_values(sort_cols, ascending=sort_asc)
            .drop_duplicates(subset=["issuer"], keep="first")
            .copy()
        )

    return df


def rank_snapshot(
    snapshot: pd.DataFrame,
    strategy: StrategyName,
    n: int,
    *,
    require_valid_price: bool = True,
    require_positive_ebitda: bool = False,
    deduplicate_issuers: bool = True,
    min_presence_63d: int = 0,
) -> list[RankedHolding]:
    """Rank a cross-sectional snapshot according to ``strategy`` and return top ``n`` holdings."""
    if n <= 0:
        raise ValueError("Portfolio size n must be positive")

    is_mf = strategy == "magic_formula"
    df = _filter_and_deduplicate(
        snapshot,
        require_roic=is_mf,
        require_valid_price=require_valid_price,
        require_positive_ebitda=require_positive_ebitda,
        deduplicate_issuers=deduplicate_issuers,
        min_presence_63d=min_presence_63d,
    )
    if df.empty:
        return []

    if strategy == "acquirers_multiple":
        df["nota"] = df["earnings_yield"]
        df["rank_yield"] = df["earnings_yield"].rank(ascending=False, method="average")
        df["rank_roic"] = np.nan
        df = df.sort_values(["nota", "ativo"], ascending=[False, True])
    elif strategy == "magic_formula":
        df["rank_yield"] = df["earnings_yield"].rank(ascending=False, method="average")
        df["rank_roic"] = df["ROIC"].rank(ascending=False, method="average")
        df["nota"] = df["rank_yield"] + df["rank_roic"]
        df = df.sort_values(["nota", "earnings_yield", "ativo"], ascending=[True, False, True])
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    selected = df.head(n)
    k = len(selected)
    if k == 0:
        return []
    weight = 1.0 / k

    holdings: list[RankedHolding] = []
    for row in selected.itertuples(index=False):
        pr = float(row.Price) if hasattr(row, "Price") and pd.notna(row.Price) else None
        roic_val = float(row.ROIC) if hasattr(row, "ROIC") and pd.notna(row.ROIC) else None
        rk_y = float(row.rank_yield) if pd.notna(row.rank_yield) else None
        rk_r = float(row.rank_roic) if pd.notna(row.rank_roic) else None
        holdings.append(
            RankedHolding(
                ticker=str(row.ativo),
                company_name=str(getattr(row, "company_name", row.ativo)),
                issuer=str(getattr(row, "issuer", row.ativo)),
                weight=weight,
                score=float(row.nota),
                earnings_yield=float(row.earnings_yield),
                roic=roic_val,
                ev=float(row.EV),
                ebitda=float(row.EBITDA),
                price=pr,
                rank_yield=rk_y,
                rank_roic=rk_r,
            )
        )
    return holdings


def rank_dataset_on_date(
    dataset: MarketDataset,
    as_of: date,
    strategy: StrategyName,
    n: int,
    *,
    ebitda_mode: EbitdaMode = "ltm",
    reporting_lag_days: int = 0,
    max_staleness_days: int = 450,
    deduplicate_issuers: bool = True,
    exclude_ebitda_12m_files: bool = False,
    require_valid_price: bool = True,
    require_positive_ebitda: bool = False,
    min_presence_63d: int = 0,
    require_exact_date: bool = False,
) -> list[RankedHolding]:
    snap = dataset.snapshot_fundamentals(
        as_of,
        ebitda_mode=ebitda_mode,
        reporting_lag_days=reporting_lag_days,
        max_staleness_days=max_staleness_days,
        exclude_ebitda_12m_files=exclude_ebitda_12m_files,
        require_exact_date=require_exact_date,
    )
    return rank_snapshot(
        snap,
        strategy=strategy,
        n=n,
        require_valid_price=require_valid_price,
        require_positive_ebitda=require_positive_ebitda,
        deduplicate_issuers=deduplicate_issuers,
        min_presence_63d=min_presence_63d,
    )
