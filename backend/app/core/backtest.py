"""Quantitative portfolio backtest simulator for Acquirer's Multiple and Magic Formula."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

from backend.app.core.data_loader import EbitdaMode, MarketDataset
from backend.app.core.metrics import (
    PerformanceSummary,
    build_performance_summary,
    compute_drawdown_series,
)
from backend.app.core.ranking import RankedHolding, StrategyName, rank_dataset_on_date

RebalanceFrequency = Literal["annual", "semiannual", "quarterly", "monthly", "buy_and_hold"]
ContributionMode = Literal["equal_current", "underweight"]

REBALANCE_MONTHS_MAP: dict[str, int | None] = {
    "monthly": 1,
    "quarterly": 3,
    "semiannual": 6,
    "annual": 12,
    "buy_and_hold": None,
}

PRESET_WINDOWS_YEARS = (1, 3, 5, 10, 15, 20)


def subtract_years(anchor: date, years: int) -> date:
    target_year = max(1, anchor.year - years)
    max_day = calendar.monthrange(target_year, anchor.month)[1]
    return date(target_year, anchor.month, min(anchor.day, max_day))


def add_months(anchor: date, months: int) -> date:
    total_months = (anchor.year * 12 + (anchor.month - 1)) + months
    target_year = total_months // 12
    target_month = (total_months % 12) + 1
    max_day = calendar.monthrange(target_year, target_month)[1]
    return date(target_year, target_month, min(anchor.day, max_day))


@dataclass(slots=True)
class BacktestConfig:
    portfolio_size: int = 20
    initial_capital: float = 10_000.0
    monthly_contribution: float = 0.0
    contribution_mode: ContributionMode = "underweight"
    rebalance_frequency: RebalanceFrequency = "annual"
    window_years: int | None = 5  # 1, 3, 5, 10, 15, 20 or None if using custom start_date
    start_date: date | None = None
    end_date: date | None = None
    ebitda_mode: EbitdaMode = "ltm"
    reporting_lag_days: int = 0
    deduplicate_issuers: bool = True
    exclude_ebitda_12m_files: bool = False
    require_positive_ebitda: bool = True
    min_presence_63d: int = 10
    risk_free_rate_annual: float = 0.0


@dataclass(slots=True)
class RebalanceEvent:
    date: str
    portfolio_equity: float
    holdings_count: int
    turnover_tickers_added: list[str]
    turnover_tickers_removed: list[str]
    holdings: list[RankedHolding]


@dataclass(slots=True)
class EquityCurvePoint:
    date: str
    equity: float
    invested: float
    quota: float  # Base 100.0
    twr_pct: float
    drawdown_pct: float


@dataclass(slots=True)
class StrategyBacktestResult:
    strategy: StrategyName
    requested_start_date: str
    effective_start_date: str
    effective_end_date: str
    window_clamped: bool
    summary: PerformanceSummary
    curve: list[EquityCurvePoint]
    rebalances: list[RebalanceEvent]


def resolve_window_row_indices(
    dataset: MarketDataset,
    config: BacktestConfig,
) -> tuple[np.ndarray, date, bool]:
    """Return ``(dataset_row_indices_for_trading_days, requested_start_date, window_clamped)``."""
    if len(dataset.trading_dates) < 2:
        raise ValueError("A base de dados precisa conter precos de fechamento em pelo menos 2 pregoes.")

    end_target = config.end_date or dataset.max_date
    end_pos = int(dataset.trading_dates.searchsorted(np.datetime64(end_target), side="right")) - 1
    if end_pos < 1:
        raise ValueError(f"Data final ({end_target.isoformat()}) anterior ao inicio dos pregoes na base.")
    effective_end_ts = dataset.trading_dates[end_pos]
    effective_end_dt = effective_end_ts.date()

    if config.start_date is not None:
        req_start = config.start_date
    elif config.window_years is not None:
        req_start = subtract_years(effective_end_dt, config.window_years)
    else:
        req_start = dataset.min_date

    window_clamped = req_start < dataset.min_date
    start_pos = int(dataset.trading_dates.searchsorted(np.datetime64(req_start), side="left"))
    if start_pos >= end_pos:
        raise ValueError(
            f"Janela invalida: data inicial ({req_start.isoformat()}) >= data final ({effective_end_dt.isoformat()})."
        )

    selected_ts = dataset.trading_dates[start_pos : end_pos + 1]
    row_indices = dataset.dates.get_indexer(selected_ts)
    return row_indices, req_start, window_clamped


def _downsample_indices(n_points: int, max_points: int = 1200) -> np.ndarray:
    if n_points <= max_points:
        return np.arange(n_points, dtype=np.int32)
    step = max(1, n_points // max_points)
    idx = np.arange(0, n_points, step, dtype=np.int32)
    if idx[-1] != n_points - 1:
        idx = np.append(idx, n_points - 1)
    return idx


def run_strategy_backtest(
    dataset: MarketDataset,
    strategy: StrategyName,
    config: BacktestConfig,
    *,
    include_curve: bool = True,
    include_rebalances: bool = True,
) -> StrategyBacktestResult:
    """Execute daily mark-to-market simulation with configurable rebalancing and monthly DCA."""
    row_indices, req_start, window_clamped = resolve_window_row_indices(dataset, config)
    all_sim_dates = [dataset.dates[int(r)].date() for r in row_indices]

    # Adapt min_presence_63d if dataset itself has fewer rows (e.g. small test fixtures)
    total_trading_rows = len(dataset.trading_dates)
    eff_min_presence = min(config.min_presence_63d, max(0, total_trading_rows // 3))

    # Locate the first trading day in the window that yields >=1 eligible stock
    first_valid_offset: int | None = None
    initial_holdings: list[RankedHolding] = []
    probe_step = 1 if len(row_indices) <= 60 else 5

    for offset in range(0, len(row_indices) - 1, probe_step):
        cand_holdings = rank_dataset_on_date(
            dataset,
            all_sim_dates[offset],
            strategy,
            config.portfolio_size,
            ebitda_mode=config.ebitda_mode,
            reporting_lag_days=config.reporting_lag_days,
            deduplicate_issuers=config.deduplicate_issuers,
            exclude_ebitda_12m_files=config.exclude_ebitda_12m_files,
            require_valid_price=True,
            require_positive_ebitda=config.require_positive_ebitda,
            min_presence_63d=eff_min_presence,
        )
        if cand_holdings:
            # Refine exact day if probe_step > 1
            exact_offset = offset
            for back in range(max(0, offset - probe_step + 1), offset + 1):
                chk = rank_dataset_on_date(
                    dataset,
                    all_sim_dates[back],
                    strategy,
                    config.portfolio_size,
                    ebitda_mode=config.ebitda_mode,
                    reporting_lag_days=config.reporting_lag_days,
                    deduplicate_issuers=config.deduplicate_issuers,
                    exclude_ebitda_12m_files=config.exclude_ebitda_12m_files,
                    require_valid_price=True,
                    require_positive_ebitda=config.require_positive_ebitda,
                    min_presence_63d=eff_min_presence,
                )
                if chk:
                    exact_offset = back
                    cand_holdings = chk
                    break
            first_valid_offset = exact_offset
            initial_holdings = cand_holdings
            break

    if first_valid_offset is None or not initial_holdings:
        raise ValueError(
            f"Nenhum ativo elegivel encontrado para '{strategy}' na janela solicitada "
            f"({req_start.isoformat()} ate {all_sim_dates[-1].isoformat()})."
        )

    if first_valid_offset > 0:
        window_clamped = True
        row_indices = row_indices[first_valid_offset:]
        all_sim_dates = all_sim_dates[first_valid_offset:]

    n_days = len(row_indices)
    n_tickers = len(dataset.tickers)
    prices_ffill = dataset.prices_ffill
    last_valid_row = dataset.last_valid_price_row
    last_valid_val = dataset.last_valid_price_val
    ticker_to_idx = dataset.ticker_to_idx

    shares = np.zeros(n_tickers, dtype=np.float64)
    held_indices = np.array([], dtype=np.int32)
    last_price = np.zeros(n_tickers, dtype=np.float64)

    cash = float(config.initial_capital)
    total_invested = float(config.initial_capital)
    quota = 100.0
    contributions_count = 0
    cashflows: list[tuple[date, float]] = [(all_sim_dates[0], -float(config.initial_capital))]

    rebalances: list[RebalanceEvent] = []
    rebalance_months = REBALANCE_MONTHS_MAP[config.rebalance_frequency]

    def _apply_rebalance(day_idx: int, dt: date, holdings: list[RankedHolding]) -> None:
        nonlocal cash, shares, held_indices
        row_i = int(row_indices[day_idx])
        prev_set = {dataset.tickers[int(i)] for i in held_indices if shares[int(i)] > 0}
        new_set = {h.ticker for h in holdings}

        # Liquidate everything at current mark-to-market price
        total_equity = cash
        if len(held_indices) > 0:
            total_equity += float(np.dot(shares[held_indices], last_price[held_indices]))
        shares.fill(0.0)

        if not holdings or total_equity <= 0.0:
            cash = total_equity
            held_indices = np.array([], dtype=np.int32)
            return

        new_idx_list: list[int] = []
        valid_holdings: list[RankedHolding] = []
        for h in holdings:
            c_idx = ticker_to_idx[h.ticker]
            px = float(prices_ffill[row_i, c_idx])
            if np.isfinite(px) and px > 0.0:
                new_idx_list.append(c_idx)
                valid_holdings.append(h)

        if not valid_holdings:
            cash = total_equity
            held_indices = np.array([], dtype=np.int32)
            return

        alloc_each = total_equity / len(valid_holdings)
        weight_each = 1.0 / len(valid_holdings)
        for c_idx, h in zip(new_idx_list, valid_holdings):
            px = float(prices_ffill[row_i, c_idx])
            shares[c_idx] = alloc_each / px
            last_price[c_idx] = px
            h.weight = weight_each
            h.price = px

        cash = 0.0
        held_indices = np.array(new_idx_list, dtype=np.int32)

        if include_rebalances:
            rebalances.append(
                RebalanceEvent(
                    date=dt.isoformat(),
                    portfolio_equity=round(total_equity, 2),
                    holdings_count=len(valid_holdings),
                    turnover_tickers_added=sorted(new_set - prev_set),
                    turnover_tickers_removed=sorted(prev_set - new_set),
                    holdings=valid_holdings,
                )
            )
        else:
            rebalances.append(
                RebalanceEvent(
                    date=dt.isoformat(),
                    portfolio_equity=round(total_equity, 2),
                    holdings_count=len(valid_holdings),
                    turnover_tickers_added=[],
                    turnover_tickers_removed=[],
                    holdings=[],
                )
            )

    def _deploy_cash_to_current(row_i: int) -> None:
        nonlocal cash
        if cash <= 0.0 or len(held_indices) == 0:
            return
        cur_px = prices_ffill[row_i, held_indices]
        tradable_mask = np.isfinite(cur_px) & (cur_px > 0.0)
        active_cols = held_indices[tradable_mask]
        active_px = cur_px[tradable_mask]
        if len(active_cols) == 0:
            return

        if config.contribution_mode == "underweight":
            cur_vals = shares[active_cols] * active_px
            post_total = float(np.sum(cur_vals)) + cash
            target_each = post_total / len(active_cols)
            deficits = np.maximum(0.0, target_each - cur_vals)
            def_sum = float(np.sum(deficits))
            if def_sum > 1e-9:
                allocs = cash * (deficits / def_sum)
            else:
                allocs = np.full(len(active_cols), cash / len(active_cols), dtype=np.float64)
        else:
            allocs = np.full(len(active_cols), cash / len(active_cols), dtype=np.float64)

        shares[active_cols] += allocs / active_px
        last_price[active_cols] = active_px
        cash = 0.0

    # Day 0 setup
    start_dt = all_sim_dates[0]
    _apply_rebalance(0, start_dt, initial_holdings)
    next_rebalance_dt = add_months(start_dt, rebalance_months) if rebalance_months is not None else None
    last_contrib_ym = (start_dt.year, start_dt.month)

    equities = np.empty(n_days, dtype=np.float64)
    invested_arr = np.empty(n_days, dtype=np.float64)
    quotas = np.empty(n_days, dtype=np.float64)

    v_day0 = cash + (
        float(np.dot(shares[held_indices], last_price[held_indices])) if len(held_indices) > 0 else 0.0
    )
    equities[0] = v_day0
    invested_arr[0] = total_invested
    quotas[0] = quota
    v_prev_post = v_day0

    for day_idx in range(1, n_days):
        row_i = int(row_indices[day_idx])
        dt = all_sim_dates[day_idx]

        # 1. Update prices & handle delistings before external cashflows
        if len(held_indices) > 0:
            row_prices = prices_ffill[row_i, held_indices]
            finite_mask = np.isfinite(row_prices) & (row_prices > 0.0)
            if np.all(finite_mask):
                last_price[held_indices] = row_prices
            else:
                valid_cols = held_indices[finite_mask]
                last_price[valid_cols] = row_prices[finite_mask]

                missing_cols = held_indices[~finite_mask]
                still_held: list[int] = list(valid_cols)
                for m_col in missing_cols:
                    # Permanently delisted if current row exceeds last_valid_row and ffill expired
                    if last_valid_row[m_col] >= 0 and row_i > last_valid_row[m_col]:
                        settle_px = (
                            float(last_valid_val[m_col])
                            if np.isfinite(last_valid_val[m_col]) and last_valid_val[m_col] > 0
                            else float(last_price[m_col])
                        )
                        cash += float(shares[m_col]) * settle_px
                        shares[m_col] = 0.0
                    else:
                        still_held.append(int(m_col))
                held_indices = np.array(sorted(still_held), dtype=np.int32)

        v_pre = cash + (
            float(np.dot(shares[held_indices], last_price[held_indices])) if len(held_indices) > 0 else 0.0
        )
        if v_prev_post > 0.0 and v_pre >= 0.0:
            quota = quota * (v_pre / v_prev_post)

        # 2. Monthly contribution on the first trading day of each new calendar month
        ym = (dt.year, dt.month)
        if config.monthly_contribution > 0.0 and ym != last_contrib_ym:
            contrib = float(config.monthly_contribution)
            cash += contrib
            total_invested += contrib
            contributions_count += 1
            cashflows.append((dt, -contrib))
            last_contrib_ym = ym
        elif ym != last_contrib_ym:
            last_contrib_ym = ym

        # 3. Scheduled portfolio rebalance (if due)
        did_rebalance = False
        if next_rebalance_dt is not None and dt >= next_rebalance_dt:
            new_holdings = rank_dataset_on_date(
                dataset,
                dt,
                strategy,
                config.portfolio_size,
                ebitda_mode=config.ebitda_mode,
                reporting_lag_days=config.reporting_lag_days,
                deduplicate_issuers=config.deduplicate_issuers,
                exclude_ebitda_12m_files=config.exclude_ebitda_12m_files,
                require_valid_price=True,
                require_positive_ebitda=config.require_positive_ebitda,
                min_presence_63d=eff_min_presence,
            )
            if new_holdings:
                _apply_rebalance(day_idx, dt, new_holdings)
                did_rebalance = True
            # Advance schedule anchored to start_dt cycle so drift doesn't accumulate
            assert rebalance_months is not None
            while next_rebalance_dt <= dt:
                next_rebalance_dt = add_months(next_rebalance_dt, rebalance_months)

        # 4. If cash is positive (monthly contribution or delisting proceeds) and we didn't just rebalance, invest it
        if not did_rebalance and cash > 0.0:
            _deploy_cash_to_current(row_i)

        v_post = cash + (
            float(np.dot(shares[held_indices], last_price[held_indices])) if len(held_indices) > 0 else 0.0
        )
        equities[day_idx] = v_post
        invested_arr[day_idx] = total_invested
        quotas[day_idx] = quota
        v_prev_post = v_post

    summary = build_performance_summary(
        dates=all_sim_dates,
        quotas=quotas,
        equities=equities,
        cashflows=cashflows,
        initial_capital=config.initial_capital,
        monthly_contribution=config.monthly_contribution,
        contributions_count=contributions_count,
        rebalances_count=len(rebalances),
        risk_free_rate_annual=config.risk_free_rate_annual,
    )

    curve: list[EquityCurvePoint] = []
    if include_curve:
        dd_full = compute_drawdown_series(quotas)
        sample_idx = _downsample_indices(n_days, max_points=1200)
        for i in sample_idx:
            q_val = float(quotas[i])
            curve.append(
                EquityCurvePoint(
                    date=all_sim_dates[int(i)].isoformat(),
                    equity=round(float(equities[i]), 2),
                    invested=round(float(invested_arr[i]), 2),
                    quota=round(q_val, 4),
                    twr_pct=round(q_val - 100.0, 4),
                    drawdown_pct=round(float(dd_full[i]), 4),
                )
            )

    return StrategyBacktestResult(
        strategy=strategy,
        requested_start_date=req_start.isoformat(),
        effective_start_date=all_sim_dates[0].isoformat(),
        effective_end_date=all_sim_dates[-1].isoformat(),
        window_clamped=window_clamped,
        summary=summary,
        curve=curve,
        rebalances=rebalances if include_rebalances else [],
    )
