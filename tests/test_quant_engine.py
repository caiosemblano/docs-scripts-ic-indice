"""Automated tests for Economatica ingestion, audit separation, rankings, DCA backtest, and API."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np
import openpyxl
import pytest

from backend.app.core.backtest import BacktestConfig, run_strategy_backtest
from backend.app.core.data_loader import MarketDataManager
from backend.app.core.metrics import compute_xirr
from backend.app.main import app
from scripts.acquirers_multiple import rank_acquirers_multiple
from scripts.audit_economatica_files import audit_directory, separate_files
from scripts.magic_formula import rank_magic_formula


def _write_economatica_xlsx(
    path: Path,
    *,
    sheet_name: str,
    company_name: str,
    ebitda_months: int = 3,
    rows: list[tuple[date, float | str, float | str, float | str, float | str]],
) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = sheet_name

    ws["A1"] = company_name
    ws["E1"] = "Economatica"
    ws["A4"] = "Data"
    ws["B4"] = "Fechamento\najust p/ prov\nEm moeda orig"
    ws["C4"] = f" EBITDA\n Em moeda orig\n em milhares\n de {ebitda_months} meses\n consolid:sim*"
    ws["D4"] = "EV\nEm moeda orig\nem milhares\nconsolid:sim*"
    ws["E4"] = " ROIC (IC fim) %\n de 12 meses\n consolid:sim*"

    for idx, (dt, price, ebitda, ev, roic) in enumerate(rows, start=5):
        ws.cell(row=idx, column=1, value=dt.isoformat())
        ws.cell(row=idx, column=2, value=price)
        ws.cell(row=idx, column=3, value=ebitda)
        ws.cell(row=idx, column=4, value=ev)
        ws.cell(row=idx, column=5, value=roic)

    wb.save(path)


def _generate_synthetic_economatica_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "economatica_sample"
    data_dir.mkdir(parents=True, exist_ok=True)

    start = date(2022, 1, 3)
    all_days = [start + timedelta(days=i) for i in range(1100) if (start + timedelta(days=i)).weekday() < 5]
    # Pick last trading day of each quarter (months 3, 6, 9, 12)
    q_dates_set: set[date] = set()
    for i, d in enumerate(all_days):
        if d.month in (3, 6, 9, 12):
            if i == len(all_days) - 1 or all_days[i + 1].month != d.month:
                q_dates_set.add(d)

    specs = [
        # High yield + high ROIC winner (grows ~25% per year)
        ("ALFA3", "ALFA3 ON.xlsx", "Alfa Energia ON", 3, 10.0, 0.0009, 50_000.0, 400_000.0, 24.0),
        # Lower liquidity duplicate class of Alfa (should be deduplicated in favor of ALFA3)
        ("ALFA4", "ALFA4 PN.xlsx", "Alfa Energia PN", 3, 9.5, 0.0009, 50_000.0, 400_000.0, 24.0),
        # Solid value stock
        ("BETA3", "BETA3.xlsx", "Beta Logistica ON", 3, 20.0, 0.0004, 35_000.0, 500_000.0, 16.0),
        # Expensive / lower ROIC stock
        ("GAMA3", "GAMA3.xlsx", "Gama Varejo ON", 3, 50.0, 0.0001, 10_000.0, 900_000.0, 6.0),
        # 12-month EBITDA export file
        ("TTEN3", "3tentos ON TTEN3.xlsx", "3tentos ON", 12, 12.0, 0.0005, 120_000.0, 600_000.0, 18.0),
    ]

    for ticker, fname, cname, eb_win, p0, daily_drift, q_ebitda, ev_val, roic_val in specs:
        rows = []
        px = p0
        for i, d in enumerate(all_days):
            px = px * (1.0 + daily_drift)
            # Make ALFA4 skip every other trading day so ALFA3 wins presence_63d
            price_cell: float | str = "-" if (ticker == "ALFA4" and i % 2 == 1) else round(px, 4)
            is_q = d in q_dates_set
            eb_cell: float | str = q_ebitda if is_q else "-"
            roic_cell: float | str = roic_val if is_q else "-"
            rows.append((d, price_cell, eb_cell, ev_val, roic_cell))

        _write_economatica_xlsx(
            data_dir / fname,
            sheet_name=ticker,
            company_name=cname,
            ebitda_months=eb_win,
            rows=rows,
        )

    # Duplicate copy file (1).xlsx
    _write_economatica_xlsx(
        data_dir / "BETA3 (1).xlsx",
        sheet_name="BETA3",
        company_name="Beta Logistica ON",
        ebitda_months=3,
        rows=[(start, 20.0, 35_000.0, 500_000.0, 16.0)],
    )

    # Invalid non-Economatica workbook
    wb_bad = openpyxl.Workbook()
    ws_bad = wb_bad.active
    assert ws_bad is not None
    ws_bad["A1"] = "Tabela Price"
    ws_bad["B1"] = "Saldo Devedor"
    wb_bad.save(data_dir / "Aula_Inatel.xlsx")

    return data_dir


def test_audit_and_separate_12m_duplicates_and_invalid(tmp_path: Path) -> None:
    data_dir = _generate_synthetic_economatica_dir(tmp_path)
    audit = audit_directory(data_dir)

    assert audit.total_files == 7
    assert audit.valid_3m_count == 4  # ALFA3, ALFA4, BETA3, GAMA3
    assert audit.ebitda_12m_count == 1  # TTEN3
    assert audit.duplicate_count == 1  # BETA3 (1).xlsx
    assert audit.invalid_count == 1  # Aula_Inatel.xlsx
    assert audit.ebitda_12m_records[0].ticker == "TTEN3"

    counts = separate_files(
        audit,
        out_12m_dir=tmp_path / "sep_12m",
        out_dup_dir=tmp_path / "sep_dup",
        out_invalid_dir=tmp_path / "sep_inv",
        copy_only=True,
    )
    assert counts == {"ebitda_12m": 1, "duplicate": 1, "invalid": 1}
    assert (tmp_path / "sep_12m" / "3tentos ON TTEN3.xlsx").is_file()
    assert (tmp_path / "sep_dup" / "BETA3 (1).xlsx").is_file()
    assert (tmp_path / "sep_inv" / "Aula_Inatel.xlsx").is_file()


def test_ltm_summation_issuer_dedup_and_cli_rankings(tmp_path: Path) -> None:
    data_dir = _generate_synthetic_economatica_dir(tmp_path)
    mgr = MarketDataManager(cache_root=tmp_path / ".cache")
    ds = mgr.load(data_dir)

    # After 4 quarterly observations (~2023-06-01), ALFA3 has quarterly EBITDA = 50,000 -> LTM = 200,000
    snap = ds.snapshot_fundamentals(date(2024, 6, 10), ebitda_mode="ltm")
    alfa3_row = snap.loc[snap["ativo"] == "ALFA3"].iloc[0]
    assert alfa3_row["EBITDA"] == pytest.approx(200_000.0)  # 4 * 50,000

    # TTEN3 was exported as 12m = 120,000 -> kept directly as 120,000 (not multiplied by 4)
    tten3_row = snap.loc[snap["ativo"] == "TTEN3"].iloc[0]
    assert tten3_row["EBITDA"] == pytest.approx(120_000.0)

    # CLI ranking deduplicates ALFA3 vs ALFA4 (picking ALFA3 due to higher presence_63d)
    am_top2 = rank_acquirers_multiple(data_dir, "2024-06-10", 2, deduplicate_issuers=True)
    tickers_am = [t for t, _, _ in am_top2]
    assert tickers_am[0] == "ALFA3"
    assert "ALFA4" not in tickers_am
    assert sum(w for _, _, w in am_top2) == pytest.approx(1.0)

    mf_top2 = rank_magic_formula(data_dir, "2024-06-10", 2, deduplicate_issuers=True)
    tickers_mf = [t for t, _, _ in mf_top2]
    assert tickers_mf[0] == "ALFA3"
    assert "ALFA4" not in tickers_mf


def test_twr_invariance_with_monthly_contributions_on_flat_prices(tmp_path: Path) -> None:
    """When asset prices stay completely flat, monthly contributions must NOT distort TWR/CAGR/XIRR."""
    flat_dir = tmp_path / "flat_market"
    flat_dir.mkdir()
    start = date(2023, 1, 2)
    days = [start + timedelta(days=i) for i in range(400) if (start + timedelta(days=i)).weekday() < 5]

    for ticker in ("FLAT3", "STEADY3"):
        rows = [(d, 10.0, 1000.0, 10_000.0, 15.0) for d in days]
        _write_economatica_xlsx(
            flat_dir / f"{ticker}.xlsx",
            sheet_name=ticker,
            company_name=ticker,
            ebitda_months=12,
            rows=rows,
        )

    mgr = MarketDataManager(cache_root=tmp_path / ".cache")
    ds = mgr.load(flat_dir)
    cfg = BacktestConfig(
        portfolio_size=2,
        initial_capital=10_000.0,
        monthly_contribution=1_000.0,
        window_years=1,
        rebalance_frequency="annual",
    )
    res = run_strategy_backtest(ds, "acquirers_multiple", cfg)

    expected_invested = 10_000.0 + res.summary.contributions_count * 1_000.0
    assert res.summary.contributions_count >= 11
    assert res.summary.total_invested == pytest.approx(expected_invested)
    assert res.summary.final_equity == pytest.approx(expected_invested, rel=1e-6)
    assert res.summary.net_profit == pytest.approx(0.0, abs=1e-4)
    assert res.summary.twr_total_pct == pytest.approx(0.0, abs=1e-4)
    assert res.summary.cagr_pct == pytest.approx(0.0, abs=1e-4)
    assert res.summary.xirr_pct == pytest.approx(0.0, abs=1e-3)


def test_xirr_known_analytical_rate() -> None:
    # Invest 10,000 on 2024-01-01, receive 12,100 exactly 2 years later (~10% p.a.)
    d0 = date(2024, 1, 1)
    d2 = d0 + timedelta(days=int(round(2 * 365.25)))
    irr = compute_xirr([(d0, -10_000.0), (d2, 12_100.0)])
    assert irr is not None
    assert irr == pytest.approx(0.10, rel=1e-2)


def test_fastapi_endpoints_with_custom_and_preset_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = _generate_synthetic_economatica_dir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    client = TestClient(app)

    r_sum = client.get("/api/dataset/summary")
    assert r_sum.status_code == 200
    assert r_sum.json()["ebitda_12m_count"] == 1

    r_run = client.post(
        "/api/backtest/run",
        json={
            "strategies": ["acquirers_multiple", "magic_formula"],
            "window_mode": "custom",
            "start_date": "2023-07-03",
            "portfolio_size": 2,
            "initial_capital": 10000,
            "monthly_contribution": 500,
            "rebalance_frequency": "quarterly",
        },
    )
    assert r_run.status_code == 200
    body = r_run.json()
    assert "acquirers_multiple" in body["results"]
    assert "magic_formula" in body["results"]
    assert body["results"]["acquirers_multiple"]["summary"]["final_equity"] > body["results"]["acquirers_multiple"]["summary"]["total_invested"]
    assert len(body["comparison_chart"]) > 20

    r_mw = client.post(
        "/api/backtest/multi-window",
        json={
            "strategies": ["acquirers_multiple", "magic_formula"],
            "windows_years": [1, 3],
            "portfolio_size": 2,
            "initial_capital": 5000,
            "monthly_contribution": 250,
            "rebalance_frequency": "annual",
        },
    )
    assert r_mw.status_code == 200
    assert len(r_mw.json()["windows"]) == 2
