"""Performance and risk metrics for portfolio backtests (TWR, CAGR, XIRR, Volatility, Drawdown)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math

import numpy as np


@dataclass(slots=True)
class PerformanceSummary:
    start_date: str
    end_date: str
    elapsed_days: int
    elapsed_years: float
    initial_capital: float
    monthly_contribution: float
    contributions_count: int
    total_invested: float
    final_equity: float
    net_profit: float
    moic: float
    twr_total_pct: float
    cagr_pct: float
    xirr_pct: float | None
    volatility_annual_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float | None
    rebalances_count: int


def compute_xirr(cashflows: list[tuple[date, float]], max_iter: int = 100) -> float | None:
    """Compute annualized Internal Rate of Return (XIRR) as a decimal (e.g. 0.15 for 15%).

    Cash outflows (investments) must be negative and terminal portfolio value positive.
    Uses safeguarded Newton-Raphson with bisection fallback.
    """
    if len(cashflows) < 2:
        return None

    has_neg = any(cf < 0 for _, cf in cashflows)
    has_pos = any(cf > 0 for _, cf in cashflows)
    if not (has_neg and has_pos):
        return None

    d0 = cashflows[0][0]
    years = np.array([(d - d0).days / 365.25 for d, _ in cashflows], dtype=np.float64)
    amounts = np.array([cf for _, cf in cashflows], dtype=np.float64)

    if np.max(years) <= 0.0:
        return None

    def npv(rate: float) -> float:
        base = 1.0 + rate
        if base <= 0.0:
            return float("inf")
        return float(np.sum(amounts * np.power(base, -years)))

    def d_npv(rate: float) -> float:
        base = 1.0 + rate
        if base <= 0.0:
            return float("-inf")
        return float(np.sum(-years * amounts * np.power(base, -years - 1.0)))

    # Bracket search for guaranteed convergence
    low = -0.9999
    high = 10.0
    f_low = npv(low)
    f_high = npv(high)
    while f_low * f_high > 0 and high < 1e6:
        high *= 4.0
        f_high = npv(high)

    guess = 0.10
    for _ in range(max_iter):
        f_val = npv(guess)
        if abs(f_val) < 1e-7:
            return guess
        deriv = d_npv(guess)
        if deriv == 0.0 or not math.isfinite(deriv):
            break
        nxt = guess - f_val / deriv
        if nxt <= -0.9999 or nxt > high:
            break
        if abs(nxt - guess) < 1e-9:
            return nxt
        guess = nxt

    # Fallback: bisection if bracketed
    if f_low * f_high <= 0:
        a, b = low, high
        fa = f_low
        for _ in range(120):
            mid = 0.5 * (a + b)
            fm = npv(mid)
            if abs(fm) < 1e-7 or (b - a) < 1e-9:
                return mid
            if fa * fm <= 0:
                b = mid
            else:
                a = mid
                fa = fm
        return 0.5 * (a + b)

    return None


def compute_drawdown_series(quotas: np.ndarray) -> np.ndarray:
    """Return percentage drawdown series (<= 0.0, e.g. -23.5 for -23.5%)."""
    if len(quotas) == 0:
        return np.array([], dtype=np.float64)
    peaks = np.maximum.accumulate(quotas)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peaks > 0.0, (quotas / peaks - 1.0) * 100.0, 0.0)
    return dd


def build_performance_summary(
    *,
    dates: list[date],
    quotas: np.ndarray,
    equities: np.ndarray,
    cashflows: list[tuple[date, float]],
    initial_capital: float,
    monthly_contribution: float,
    contributions_count: int,
    rebalances_count: int,
    risk_free_rate_annual: float = 0.0,
) -> PerformanceSummary:
    start_d = dates[0]
    end_d = dates[-1]
    elapsed_days = max(1, (end_d - start_d).days)
    elapsed_years = elapsed_days / 365.25

    q_start = float(quotas[0]) if len(quotas) > 0 else 1.0
    q_end = float(quotas[-1]) if len(quotas) > 0 else 1.0
    ratio = (q_end / q_start) if q_start > 0 else 1.0

    twr_total_pct = (ratio - 1.0) * 100.0
    if elapsed_days >= 30 and ratio > 0:
        cagr_dec = (ratio ** (365.25 / elapsed_days)) - 1.0
    else:
        cagr_dec = ratio - 1.0
    cagr_pct = cagr_dec * 100.0

    if len(quotas) > 2:
        with np.errstate(divide="ignore", invalid="ignore"):
            daily_rets = quotas[1:] / quotas[:-1] - 1.0
        daily_rets = daily_rets[np.isfinite(daily_rets)]
        vol_dec = float(np.std(daily_rets, ddof=1) * math.sqrt(252.0)) if len(daily_rets) > 1 else 0.0
    else:
        vol_dec = 0.0
    vol_pct = vol_dec * 100.0

    dd_series = compute_drawdown_series(quotas)
    max_dd_pct = float(np.min(dd_series)) if len(dd_series) > 0 else 0.0

    sharpe: float | None = None
    if vol_dec > 1e-9:
        sharpe = (cagr_dec - risk_free_rate_annual) / vol_dec

    final_eq = float(equities[-1]) if len(equities) > 0 else initial_capital
    total_inv = float(sum(-cf for _, cf in cashflows if cf < 0))
    if total_inv <= 0:
        total_inv = initial_capital
    net_profit = final_eq - total_inv
    moic = (final_eq / total_inv) if total_inv > 0 else 1.0

    full_cfs = list(cashflows) + [(end_d, final_eq)]
    xirr_dec = compute_xirr(full_cfs)
    xirr_pct = (xirr_dec * 100.0) if xirr_dec is not None and math.isfinite(xirr_dec) else None

    return PerformanceSummary(
        start_date=start_d.isoformat(),
        end_date=end_d.isoformat(),
        elapsed_days=elapsed_days,
        elapsed_years=round(elapsed_years, 4),
        initial_capital=round(initial_capital, 2),
        monthly_contribution=round(monthly_contribution, 2),
        contributions_count=contributions_count,
        total_invested=round(total_inv, 2),
        final_equity=round(final_eq, 2),
        net_profit=round(net_profit, 2),
        moic=round(moic, 4),
        twr_total_pct=round(twr_total_pct, 4),
        cagr_pct=round(cagr_pct, 4),
        xirr_pct=round(xirr_pct, 4) if xirr_pct is not None else None,
        volatility_annual_pct=round(vol_pct, 4),
        max_drawdown_pct=round(max_dd_pct, 4),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        rebalances_count=rebalances_count,
    )
