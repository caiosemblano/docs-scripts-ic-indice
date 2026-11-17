"""Pydantic schemas for the quantitative portfolio & backtesting REST API."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.core.backtest import ContributionMode, RebalanceFrequency
from backend.app.core.data_loader import EbitdaMode
from backend.app.core.ranking import StrategyName


class AuditRecordSchema(BaseModel):
    filename: str
    ticker: str
    company_name: str
    category: str
    ebitda_window_months: int | None
    raw_ebitda_header: str
    columns_detected: str
    reason: str


class DatasetSummaryResponse(BaseModel):
    data_dir: str
    min_date: str
    max_date: str
    total_files: int
    active_tickers: int
    trading_days_count: int
    fundamental_dates_count: int
    valid_3m_count: int
    ebitda_12m_count: int
    duplicate_count: int
    invalid_count: int


class DatasetAuditResponse(BaseModel):
    summary: DatasetSummaryResponse
    ebitda_12m_records: list[AuditRecordSchema]
    duplicate_records: list[AuditRecordSchema]
    invalid_records: list[AuditRecordSchema]


class BacktestParametersSchema(BaseModel):
    strategies: list[StrategyName] = Field(
        default_factory=lambda: ["acquirers_multiple", "magic_formula"],
        min_length=1,
    )
    portfolio_size: int = Field(default=20, ge=1, le=200)
    initial_capital: float = Field(default=10_000.0, gt=0.0)
    monthly_contribution: float = Field(default=1_000.0, ge=0.0)
    contribution_mode: ContributionMode = "underweight"
    rebalance_frequency: RebalanceFrequency = "annual"
    ebitda_mode: EbitdaMode = "ltm"
    reporting_lag_days: int = Field(default=0, ge=0, le=365)
    deduplicate_issuers: bool = True
    exclude_ebitda_12m_files: bool = False
    require_positive_ebitda: bool = True
    min_presence_63d: int = Field(default=10, ge=0, le=63)
    risk_free_rate_annual: float = Field(default=0.0, ge=0.0, le=1.0)
    end_date: date | None = None


class BacktestRunRequest(BacktestParametersSchema):
    window_mode: Literal["preset", "custom"] = "custom"
    window_years: int | None = Field(default=None, ge=1, le=50)
    start_date: date | None = None

    @model_validator(mode="after")
    def _validate_window(self) -> BacktestRunRequest:
        if self.window_mode == "preset" and self.window_years is None:
            self.window_years = 20
        return self


class MultiWindowRequest(BacktestParametersSchema):
    start_date: date | None = None
    windows_years: list[int] = Field(
        default_factory=lambda: [1, 3, 5, 10, 15, 20],
        min_length=1,
    )


class RankedHoldingSchema(BaseModel):
    ticker: str
    company_name: str
    issuer: str
    weight: float
    score: float
    earnings_yield: float
    roic: float | None
    ev: float
    ebitda: float
    price: float | None
    rank_yield: float | None = None
    rank_roic: float | None = None


class RebalanceEventSchema(BaseModel):
    date: str
    portfolio_equity: float
    holdings_count: int
    turnover_tickers_added: list[str]
    turnover_tickers_removed: list[str]
    holdings: list[RankedHoldingSchema]


class EquityCurvePointSchema(BaseModel):
    date: str
    equity: float
    invested: float
    quota: float
    twr_pct: float
    drawdown_pct: float


class PerformanceSummarySchema(BaseModel):
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
    skipped_rebalances: int = 0


class StrategyResultSchema(BaseModel):
    strategy: StrategyName
    requested_start_date: str
    effective_start_date: str
    effective_end_date: str
    window_clamped: bool
    summary: PerformanceSummarySchema
    curve: list[EquityCurvePointSchema]
    rebalances: list[RebalanceEventSchema]


class ComparisonChartPointSchema(BaseModel):
    date: str
    invested: float | None = None
    acquirers_equity: float | None = None
    magic_equity: float | None = None
    acquirers_twr_pct: float | None = None
    magic_twr_pct: float | None = None
    acquirers_drawdown_pct: float | None = None
    magic_drawdown_pct: float | None = None


class BacktestRunResponse(BaseModel):
    results: dict[str, StrategyResultSchema]
    comparison_chart: list[ComparisonChartPointSchema]


class RollingSubWindowSchema(BaseModel):
    index: int
    label: str
    requested_start_date: str
    requested_end_date: str
    effective_start_date: str
    effective_end_date: str
    window_clamped: bool
    strategies: dict[str, PerformanceSummarySchema]


class RollingStrategyAggregateSchema(BaseModel):
    window_count: int
    positive_cagr_count: int
    win_rate_pct: float
    beat_other_count: int | None = None
    beat_other_pct: float | None = None
    mean_cagr_pct: float
    median_cagr_pct: float
    min_cagr_pct: float
    max_cagr_pct: float
    worst_window_label: str
    best_window_label: str
    mean_xirr_pct: float | None = None
    median_xirr_pct: float | None = None
    mean_total_invested: float
    mean_final_equity: float
    median_final_equity: float
    min_final_equity: float
    max_final_equity: float
    mean_max_drawdown_pct: float
    worst_max_drawdown_pct: float


class SkippedWindowSchema(BaseModel):
    label: str
    requested_start_date: str
    requested_end_date: str
    reason: str


class WindowComparisonEntrySchema(BaseModel):
    window_years: int
    window_count: int
    base_start_date: str
    base_end_date: str
    aggregates: dict[str, RollingStrategyAggregateSchema]
    rolling_windows: list[RollingSubWindowSchema]
    skipped_windows: list[SkippedWindowSchema] = Field(default_factory=list)
    error: str | None = None


class MultiWindowResponse(BaseModel):
    windows: list[WindowComparisonEntrySchema]
