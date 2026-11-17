"""FastAPI server for Acquirer's Multiple & Magic Formula portfolio backtesting."""

from __future__ import annotations

from dataclasses import asdict
import io
import csv
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.app.core.backtest import (
    BacktestConfig,
    StrategyBacktestResult,
    run_multi_window_rolling,
    run_strategy_backtest,
    subtract_years,
)
from backend.app.core.data_loader import MarketDataset, default_data_manager
from backend.app.schemas import (
    AuditRecordSchema,
    BacktestRunRequest,
    BacktestRunResponse,
    ComparisonChartPointSchema,
    DatasetAuditResponse,
    DatasetSummaryResponse,
    MultiWindowRequest,
    MultiWindowResponse,
    PerformanceSummarySchema,
    RollingStrategyAggregateSchema,
    RollingSubWindowSchema,
    SkippedWindowSchema,
    StrategyResultSchema,
    WindowComparisonEntrySchema,
)
from scripts.audit_economatica_files import resolve_default_data_dir

ROOT_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"


def get_configured_data_dir() -> Path:
    env_dir = os.environ.get("DATA_DIR")
    if env_dir:
        return Path(env_dir)
    return resolve_default_data_dir()


def get_dataset(*, force_rebuild: bool = False) -> MarketDataset:
    data_dir = get_configured_data_dir()
    try:
        return default_data_manager.load(data_dir, force_rebuild=force_rebuild)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _to_summary_schema(dataset: MarketDataset) -> DatasetSummaryResponse:
    audit = dataset.audit
    return DatasetSummaryResponse(
        data_dir=str(dataset.data_dir),
        min_date=dataset.min_date.isoformat(),
        max_date=dataset.max_date.isoformat(),
        total_files=audit.total_files,
        active_tickers=len(dataset.tickers),
        trading_days_count=len(dataset.trading_dates),
        fundamental_dates_count=len(dataset.fund_dates),
        valid_3m_count=audit.valid_3m_count,
        ebitda_12m_count=audit.ebitda_12m_count,
        duplicate_count=audit.duplicate_count,
        invalid_count=audit.invalid_count,
    )


def _merge_comparison_chart(
    results: dict[str, StrategyBacktestResult],
) -> list[ComparisonChartPointSchema]:
    by_date: dict[str, dict[str, float | str | None]] = {}
    for strat, res in results.items():
        prefix = "acquirers" if strat == "acquirers_multiple" else "magic"
        for pt in res.curve:
            entry = by_date.setdefault(pt.date, {"date": pt.date, "invested": pt.invested})
            if entry.get("invested") is None or pt.invested > float(entry["invested"] or 0.0):
                entry["invested"] = pt.invested
            entry[f"{prefix}_equity"] = pt.equity
            entry[f"{prefix}_twr_pct"] = pt.twr_pct
            entry[f"{prefix}_drawdown_pct"] = pt.drawdown_pct

    ordered_dates = sorted(by_date.keys())
    return [ComparisonChartPointSchema(**by_date[d]) for d in ordered_dates]  # type: ignore[arg-type]


app = FastAPI(
    title="IC Indice — Acquirer's Multiple & Magic Formula Backtester",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dataset/summary", response_model=DatasetSummaryResponse)
def dataset_summary(refresh: bool = Query(default=False)) -> DatasetSummaryResponse:
    dataset = get_dataset(force_rebuild=refresh)
    return _to_summary_schema(dataset)


@app.get("/api/dataset/audit", response_model=DatasetAuditResponse)
def dataset_audit(refresh: bool = Query(default=False)) -> DatasetAuditResponse:
    dataset = get_dataset(force_rebuild=refresh)
    audit = dataset.audit

    def _conv(recs: list) -> list[AuditRecordSchema]:
        out: list[AuditRecordSchema] = []
        for r in recs:
            d = asdict(r)
            d.pop("path", None)
            out.append(AuditRecordSchema(**d))
        return out

    return DatasetAuditResponse(
        summary=_to_summary_schema(dataset),
        ebitda_12m_records=_conv(audit.ebitda_12m_records),
        duplicate_records=_conv(audit.duplicate_records),
        invalid_records=_conv(audit.invalid_records),
    )


@app.get("/api/dataset/audit/reexport-csv")
def download_reexport_12m_csv() -> StreamingResponse:
    dataset = get_dataset(force_rebuild=False)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ticker", "company_name", "filename", "raw_ebitda_header", "reason"])
    for rec in dataset.audit.ebitda_12m_records:
        writer.writerow([rec.ticker, rec.company_name, rec.filename, rec.raw_ebitda_header, rec.reason])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="reexportar_ebitda_12m.csv"'},
    )


@app.post("/api/backtest/run", response_model=BacktestRunResponse)
def run_backtest_endpoint(payload: BacktestRunRequest) -> BacktestRunResponse:
    dataset = get_dataset(force_rebuild=False)
    end_anchor = payload.end_date or dataset.max_date
    resolved_start = payload.start_date
    resolved_years: int | None = None
    if payload.window_mode == "preset":
        resolved_years = payload.window_years
        resolved_start = None
    elif resolved_start is None:
        resolved_start = max(dataset.min_date, subtract_years(end_anchor, 20))

    cfg = BacktestConfig(
        portfolio_size=payload.portfolio_size,
        initial_capital=payload.initial_capital,
        monthly_contribution=payload.monthly_contribution,
        contribution_mode=payload.contribution_mode,
        rebalance_frequency=payload.rebalance_frequency,
        window_years=resolved_years,
        start_date=resolved_start,
        end_date=payload.end_date,
        ebitda_mode=payload.ebitda_mode,
        reporting_lag_days=payload.reporting_lag_days,
        deduplicate_issuers=payload.deduplicate_issuers,
        exclude_ebitda_12m_files=payload.exclude_ebitda_12m_files,
        require_positive_ebitda=payload.require_positive_ebitda,
        min_presence_63d=payload.min_presence_63d,
        risk_free_rate_annual=payload.risk_free_rate_annual,
        max_start_delay_days=None,
    )

    raw_results: dict[str, StrategyBacktestResult] = {}
    schema_results: dict[str, StrategyResultSchema] = {}
    errors: list[str] = []

    for strat in payload.strategies:
        try:
            res = run_strategy_backtest(
                dataset,
                strat,
                cfg,
                include_curve=True,
                include_rebalances=True,
            )
            raw_results[strat] = res
            schema_results[strat] = StrategyResultSchema(**asdict(res))
        except ValueError as exc:
            errors.append(f"{strat}: {exc}")

    if not schema_results:
        raise HTTPException(status_code=400, detail="; ".join(errors) or "Falha ao executar backtest.")

    return BacktestRunResponse(
        results=schema_results,
        comparison_chart=_merge_comparison_chart(raw_results),
    )


@app.post("/api/backtest/multi-window", response_model=MultiWindowResponse)
def run_multi_window_endpoint(payload: MultiWindowRequest) -> MultiWindowResponse:
    dataset = get_dataset(force_rebuild=False)
    base_cfg = BacktestConfig(
        portfolio_size=payload.portfolio_size,
        initial_capital=payload.initial_capital,
        monthly_contribution=payload.monthly_contribution,
        contribution_mode=payload.contribution_mode,
        rebalance_frequency=payload.rebalance_frequency,
        window_years=None,
        start_date=payload.start_date,
        end_date=payload.end_date,
        ebitda_mode=payload.ebitda_mode,
        reporting_lag_days=payload.reporting_lag_days,
        deduplicate_issuers=payload.deduplicate_issuers,
        exclude_ebitda_12m_files=payload.exclude_ebitda_12m_files,
        require_positive_ebitda=payload.require_positive_ebitda,
        min_presence_63d=payload.min_presence_63d,
        risk_free_rate_annual=payload.risk_free_rate_annual,
    )

    try:
        comparisons = run_multi_window_rolling(
            dataset=dataset,
            strategies=payload.strategies,
            base_config=base_cfg,
            windows_years=payload.windows_years,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    entries: list[WindowComparisonEntrySchema] = []
    for comp in comparisons:
        entries.append(
            WindowComparisonEntrySchema(
                window_years=comp.window_years,
                window_count=comp.window_count,
                base_start_date=comp.base_start_date,
                base_end_date=comp.base_end_date,
                aggregates={
                    k: RollingStrategyAggregateSchema(**asdict(v))
                    for k, v in comp.aggregates.items()
                },
                rolling_windows=[
                    RollingSubWindowSchema(
                        index=rw.index,
                        label=rw.label,
                        requested_start_date=rw.requested_start_date,
                        requested_end_date=rw.requested_end_date,
                        effective_start_date=rw.effective_start_date,
                        effective_end_date=rw.effective_end_date,
                        window_clamped=rw.window_clamped,
                        strategies={
                            sk: PerformanceSummarySchema(**asdict(sv))
                            for sk, sv in rw.strategies.items()
                        },
                    )
                    for rw in comp.rolling_windows
                ],
                skipped_windows=[
                    SkippedWindowSchema(
                        label=sw.label,
                        requested_start_date=sw.requested_start_date,
                        requested_end_date=sw.requested_end_date,
                        reason=sw.reason,
                    )
                    for sw in comp.skipped_windows
                ],
                error=comp.error,
            )
        )

    return MultiWindowResponse(windows=entries)


if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
