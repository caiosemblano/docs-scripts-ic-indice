"""High-performance loader and binary/Parquet cache for Economatica / Excel market datasets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from backend.app.core.economatica_xml import (
    ParsedAssetSheet,
    extract_issuer_code,
    parse_xlsx_timeseries,
)
from scripts.audit_economatica_files import AuditRecord, DatasetAuditResult, audit_directory

CACHE_SCHEMA_VERSION = "v2"
PRICE_FFILL_LIMIT = 35  # ~7 weeks of trading days (handles thin trading & staggered batch exports)
EbitdaMode = Literal["ltm", "raw"]


def _compute_ebitda_ltm(
    dates: list[date],
    raw_ebitdas: list[float],
    window_months: int | None,
) -> np.ndarray:
    """Compute LTM EBITDA at each observation date.

    - If ``window_months == 3`` (Economatica quarterly EBITDA): sums 4 consecutive valid
      quarterly observations whose span is between 200 and 420 calendar days (~4 quarters).
    - If ``window_months == 12`` or ``None``: returns ``raw_ebitdas`` directly.
    """
    arr = np.asarray(raw_ebitdas, dtype=np.float64)
    if window_months != 3:
        return arr.copy()

    valid_idx = np.flatnonzero(np.isfinite(arr))
    out = np.full_like(arr, np.nan, dtype=np.float64)
    if len(valid_idx) < 4:
        return out

    valid_vals = arr[valid_idx]
    valid_ordinals = np.array([dates[i].toordinal() for i in valid_idx], dtype=np.int64)

    for k in range(3, len(valid_idx)):
        span_days = int(valid_ordinals[k] - valid_ordinals[k - 3])
        if 200 <= span_days <= 420:
            out[valid_idx[k]] = float(
                valid_vals[k - 3] + valid_vals[k - 2] + valid_vals[k - 1] + valid_vals[k]
            )
    return out


def _parse_worker(args: tuple[str, int | None]) -> dict[str, object] | None:
    path_str, audit_win = args
    parsed: ParsedAssetSheet | None = parse_xlsx_timeseries(path_str)
    if parsed is None or not parsed.dates:
        return None

    win = parsed.ebitda_window_months if parsed.ebitda_window_months is not None else audit_win
    ltm = _compute_ebitda_ltm(parsed.dates, parsed.ebitdas, win)
    ordinals = np.array([d.toordinal() for d in parsed.dates], dtype=np.int32)
    prices = np.asarray(parsed.prices, dtype=np.float64)
    evs = np.asarray(parsed.evs, dtype=np.float64)
    ebitdas_raw = np.asarray(parsed.ebitdas, dtype=np.float64)
    roics = np.asarray(parsed.roics, dtype=np.float64)

    if len(ordinals) > 1 and np.any(np.diff(ordinals) <= 0):
        order = np.argsort(ordinals, kind="mergesort")
        ordinals = ordinals[order]
        prices = prices[order]
        evs = evs[order]
        ebitdas_raw = ebitdas_raw[order]
        ltm = ltm[order]
        roics = roics[order]
        keep = np.empty(len(ordinals), dtype=bool)
        keep[:-1] = ordinals[:-1] != ordinals[1:]
        keep[-1] = True
        ordinals = ordinals[keep]
        prices = prices[keep]
        evs = evs[keep]
        ebitdas_raw = ebitdas_raw[keep]
        ltm = ltm[keep]
        roics = roics[keep]

    prices = np.where(prices > 0.0, prices, np.nan)

    fund_mask = np.isfinite(ebitdas_raw) | np.isfinite(ltm) | np.isfinite(roics)
    price_mask = np.isfinite(prices)

    first_price_ord = int(ordinals[price_mask][0]) if np.any(price_mask) else 0
    last_price_ord = int(ordinals[price_mask][-1]) if np.any(price_mask) else 0

    return {
        "ticker": parsed.ticker,
        "company_name": parsed.company_name,
        "issuer": extract_issuer_code(parsed.ticker),
        "filename": parsed.filename,
        "ebitda_window_months": int(win) if win is not None else 0,
        "ordinals": ordinals,
        "prices": prices,
        "evs": evs,
        "fund_ordinals": ordinals[fund_mask],
        "fund_ebitda_raw": ebitdas_raw[fund_mask],
        "fund_ebitda_ltm": ltm[fund_mask],
        "fund_roic": roics[fund_mask],
        "first_price_ord": first_price_ord,
        "last_price_ord": last_price_ord,
        "trading_days_count": int(np.sum(price_mask)),
        "fundamentals_count": int(np.sum(fund_mask)),
    }


def _directory_fingerprint(data_dir: Path) -> str:
    entries: list[str] = [CACHE_SCHEMA_VERSION]
    with os.scandir(data_dir) as it:
        for entry in it:
            if entry.is_file() and entry.name.lower().endswith(".xlsx") and not entry.name.startswith("~$"):
                st = entry.stat()
                entries.append(f"{entry.name}:{st.st_size}:{st.st_mtime_ns}")
    entries.sort()
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()[:24]


def _ffill_matrix_limit(mat: np.ndarray, limit: int) -> np.ndarray:
    """Fast NumPy forward-fill along axis 0 up to ``limit`` consecutive NaN rows."""
    out = mat.copy()
    n_rows, _ = out.shape
    if n_rows <= 1 or limit <= 0:
        return out

    streak = np.zeros(out.shape[1], dtype=np.int32)
    last_val = out[0].copy()

    for r in range(1, n_rows):
        row = out[r]
        finite = np.isfinite(row)
        streak[finite] = 0
        last_val[finite] = row[finite]

        missing = ~finite
        streak[missing] += 1
        can_fill = missing & (streak <= limit) & np.isfinite(last_val)
        row[can_fill] = last_val[can_fill]

    return out


def _ffill_with_obs_ordinal(
    mat: np.ndarray,
    fund_ordinals: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Forward-fill ``mat`` along axis 0 while tracking the ordinal date of each value."""
    n_rows, n_cols = mat.shape
    out_val = mat.copy()
    out_ord = np.zeros((n_rows, n_cols), dtype=np.int32)

    if n_rows == 0:
        return out_val, out_ord

    finite0 = np.isfinite(out_val[0])
    out_ord[0, finite0] = fund_ordinals[0]

    for r in range(1, n_rows):
        row = out_val[r]
        has_new = np.isfinite(row)
        missing = ~has_new
        row[missing] = out_val[r - 1, missing]
        out_ord[r, has_new] = fund_ordinals[r]
        out_ord[r, missing] = out_ord[r - 1, missing]

    return out_val, out_ord


@dataclass
class MarketDataset:
    data_dir: Path
    audit: DatasetAuditResult
    dates: pd.DatetimeIndex
    trading_dates: pd.DatetimeIndex
    tickers: list[str]
    ticker_to_idx: dict[str, int]
    assets_meta: pd.DataFrame  # Indexed by ticker
    prices_raw: np.ndarray  # shape (len(dates), len(tickers))
    prices_ffill: np.ndarray  # shape (len(dates), len(tickers)), ffilled up to PRICE_FFILL_LIMIT
    ev_ffill: np.ndarray  # shape (len(dates), len(tickers)), ffilled up to PRICE_FFILL_LIMIT
    last_valid_price_row: np.ndarray  # shape (len(tickers),), last row idx with finite raw price (-1 if none)
    last_valid_price_val: np.ndarray  # shape (len(tickers),), last finite raw price (nan if none)
    fund_dates: pd.DatetimeIndex
    ebitda_ltm_ffill: np.ndarray
    ebitda_ltm_obs_ord: np.ndarray
    ebitda_raw_ffill: np.ndarray
    ebitda_raw_obs_ord: np.ndarray
    roic_ffill: np.ndarray
    roic_obs_ord: np.ndarray
    presence_63d: np.ndarray  # shape (len(dates), len(tickers)), rolling 63-row count of raw trades

    @property
    def min_date(self) -> date:
        base = self.trading_dates if len(self.trading_dates) > 0 else self.dates
        return base[0].date()

    @property
    def max_date(self) -> date:
        base = self.trading_dates if len(self.trading_dates) > 0 else self.dates
        return base[-1].date()

    def resolve_asof_date_idx(self, target: date, *, require_trading: bool = True) -> int | None:
        """Return index into ``self.dates`` of the latest date ``<= target``."""
        ts = pd.Timestamp(target)
        if require_trading and len(self.trading_dates) > 0:
            pos = int(self.trading_dates.searchsorted(ts, side="right")) - 1
            if pos < 0:
                return None
            matched_ts = self.trading_dates[pos]
            return int(self.dates.get_loc(matched_ts))

        pos = int(self.dates.searchsorted(ts, side="right")) - 1
        return pos if pos >= 0 else None

    def snapshot_fundamentals(
        self,
        as_of: date,
        *,
        ebitda_mode: EbitdaMode = "ltm",
        reporting_lag_days: int = 0,
        max_staleness_days: int = 450,
        exclude_ebitda_12m_files: bool = False,
        require_exact_date: bool = False,
    ) -> pd.DataFrame:
        """Build cross-sectional snapshot of ``Price, EV, EBITDA, ROIC, presence_63d`` as of ``as_of``."""
        if require_exact_date:
            ts = pd.Timestamp(as_of)
            if ts not in self.dates:
                return pd.DataFrame()
            d_idx = int(self.dates.get_loc(ts))
        else:
            has_any_prices = len(self.trading_dates) > 0
            d_idx = self.resolve_asof_date_idx(as_of, require_trading=has_any_prices)
            if d_idx is None:
                return pd.DataFrame()

        snap_date = self.dates[d_idx].date()
        price_row = self.prices_raw[d_idx] if require_exact_date else self.prices_ffill[d_idx]
        ev_row = self.ev_ffill[d_idx]
        pres_row = self.presence_63d[d_idx]

        cutoff_date = snap_date - timedelta(days=max(0, int(reporting_lag_days)))
        cutoff_ts = pd.Timestamp(cutoff_date)
        cutoff_ord = cutoff_date.toordinal()

        n_tickers = len(self.tickers)
        if len(self.fund_dates) == 0:
            ebitda_vals = np.full(n_tickers, np.nan, dtype=np.float64)
            roic_vals = np.full(n_tickers, np.nan, dtype=np.float64)
        else:
            if require_exact_date and reporting_lag_days == 0 and len(self.trading_dates) == 0:
                if cutoff_ts not in self.fund_dates:
                    return pd.DataFrame()
                f_idx = int(self.fund_dates.get_loc(cutoff_ts))
            else:
                f_idx = int(self.fund_dates.searchsorted(cutoff_ts, side="right")) - 1

            if f_idx < 0:
                ebitda_vals = np.full(n_tickers, np.nan, dtype=np.float64)
                roic_vals = np.full(n_tickers, np.nan, dtype=np.float64)
            else:
                if ebitda_mode == "ltm":
                    eb_source = self.ebitda_ltm_ffill
                    eb_ord_source = self.ebitda_ltm_obs_ord
                else:
                    eb_source = self.ebitda_raw_ffill
                    eb_ord_source = self.ebitda_raw_obs_ord
                eb_raw_slice = eb_source[f_idx].copy()
                eb_ord_slice = eb_ord_source[f_idx]
                stale_eb = (eb_ord_slice <= 0) | ((cutoff_ord - eb_ord_slice) > max_staleness_days)
                if require_exact_date and len(self.trading_dates) == 0:
                    stale_eb = eb_ord_slice != cutoff_ord
                eb_raw_slice[stale_eb] = np.nan
                ebitda_vals = eb_raw_slice

                roic_slice = self.roic_ffill[f_idx].copy()
                roic_ord_slice = self.roic_obs_ord[f_idx]
                stale_roic = (roic_ord_slice <= 0) | ((cutoff_ord - roic_ord_slice) > max_staleness_days)
                if require_exact_date and len(self.trading_dates) == 0:
                    stale_roic = roic_ord_slice != cutoff_ord
                roic_slice[stale_roic] = np.nan
                roic_vals = roic_slice

        df = pd.DataFrame(
            {
                "ativo": self.tickers,
                "company_name": self.assets_meta["company_name"].to_numpy(),
                "issuer": self.assets_meta["issuer"].to_numpy(),
                "ebitda_window_months": self.assets_meta["ebitda_window_months"].to_numpy(),
                "Price": price_row,
                "EV": ev_row,
                "EBITDA": ebitda_vals,
                "ROIC": roic_vals,
                "presence_63d": pres_row,
            }
        )

        if exclude_ebitda_12m_files:
            df = df.loc[df["ebitda_window_months"] != 12]

        return df


def _build_runtime_dataset(
    data_dir: Path,
    audit: DatasetAuditResult,
    all_ordinals: np.ndarray,
    tickers: list[str],
    price_mat: np.ndarray,
    ev_mat: np.ndarray,
    fundamentals_df: pd.DataFrame,
    assets_meta_df: pd.DataFrame,
) -> MarketDataset:
    assets_meta = assets_meta_df.set_index("ticker").reindex(tickers)
    dates = pd.DatetimeIndex([date.fromordinal(int(o)) for o in all_ordinals])
    ticker_to_idx = {t: i for i, t in enumerate(tickers)}

    has_trade = np.any(np.isfinite(price_mat), axis=1)
    trading_dates = dates[has_trade]

    prices_ffill = _ffill_matrix_limit(price_mat, PRICE_FFILL_LIMIT)
    ev_ffill = _ffill_matrix_limit(ev_mat, PRICE_FFILL_LIMIT)

    # Last finite raw price index & value per ticker (for clean delisting settlement)
    n_dates, n_tickers = price_mat.shape
    last_valid_row = np.full(n_tickers, -1, dtype=np.int32)
    last_valid_val = np.full(n_tickers, np.nan, dtype=np.float64)
    for c in range(n_tickers):
        valid_rows = np.flatnonzero(np.isfinite(price_mat[:, c]))
        if len(valid_rows) > 0:
            lr = int(valid_rows[-1])
            last_valid_row[c] = lr
            last_valid_val[c] = float(price_mat[lr, c])

    finite_price_int = np.isfinite(price_mat).astype(np.int16)
    csum = np.cumsum(finite_price_int, axis=0, dtype=np.int32)
    presence_63d = csum.copy()
    if n_dates > 63:
        presence_63d[63:] = csum[63:] - csum[:-63]

    if fundamentals_df.empty:
        fund_dates = pd.DatetimeIndex([])
        empty_f = np.empty((0, n_tickers), dtype=np.float64)
        empty_o = np.empty((0, n_tickers), dtype=np.int32)
        eb_ltm_ff, eb_ltm_obs = empty_f, empty_o
        eb_raw_ff, eb_raw_obs = empty_f, empty_o
        roic_ff, roic_obs = empty_f, empty_o
    else:
        unique_ords = np.unique(fundamentals_df["ordinal"].to_numpy(dtype=np.int32))
        fund_dates = pd.DatetimeIndex([date.fromordinal(int(o)) for o in unique_ords])
        n_fund = len(unique_ords)

        eb_ltm_mat = np.full((n_fund, n_tickers), np.nan, dtype=np.float64)
        eb_raw_mat = np.full((n_fund, n_tickers), np.nan, dtype=np.float64)
        roic_mat = np.full((n_fund, n_tickers), np.nan, dtype=np.float64)

        row_pos = np.searchsorted(unique_ords, fundamentals_df["ordinal"].to_numpy(dtype=np.int32))
        col_pos = np.array([ticker_to_idx[t] for t in fundamentals_df["ticker"]], dtype=np.int32)

        eb_ltm_mat[row_pos, col_pos] = fundamentals_df["ebitda_ltm"].to_numpy(dtype=np.float64)
        eb_raw_mat[row_pos, col_pos] = fundamentals_df["ebitda_raw"].to_numpy(dtype=np.float64)
        roic_mat[row_pos, col_pos] = fundamentals_df["roic"].to_numpy(dtype=np.float64)

        eb_ltm_ff, eb_ltm_obs = _ffill_with_obs_ordinal(eb_ltm_mat, unique_ords)
        eb_raw_ff, eb_raw_obs = _ffill_with_obs_ordinal(eb_raw_mat, unique_ords)
        roic_ff, roic_obs = _ffill_with_obs_ordinal(roic_mat, unique_ords)

    return MarketDataset(
        data_dir=data_dir,
        audit=audit,
        dates=dates,
        trading_dates=trading_dates,
        tickers=tickers,
        ticker_to_idx=ticker_to_idx,
        assets_meta=assets_meta,
        prices_raw=price_mat,
        prices_ffill=prices_ffill,
        ev_ffill=ev_ffill,
        last_valid_price_row=last_valid_row,
        last_valid_price_val=last_valid_val,
        fund_dates=fund_dates,
        ebitda_ltm_ffill=eb_ltm_ff,
        ebitda_ltm_obs_ord=eb_ltm_obs,
        ebitda_raw_ffill=eb_raw_ff,
        ebitda_raw_obs_ord=eb_raw_obs,
        roic_ffill=roic_ff,
        roic_obs_ord=roic_obs,
        presence_63d=presence_63d,
    )


def _serialize_audit(audit: DatasetAuditResult) -> dict[str, object]:
    return {
        "data_dir": audit.data_dir,
        "total_files": audit.total_files,
        "valid_3m_count": audit.valid_3m_count,
        "ebitda_12m_count": audit.ebitda_12m_count,
        "duplicate_count": audit.duplicate_count,
        "invalid_count": audit.invalid_count,
        "records": [asdict(r) for r in audit.records],
    }


def _deserialize_audit(payload: dict[str, object]) -> DatasetAuditResult:
    recs = [AuditRecord(**r) for r in payload.get("records", [])]  # type: ignore[arg-type]
    return DatasetAuditResult(
        data_dir=str(payload["data_dir"]),
        total_files=int(payload["total_files"]),  # type: ignore[arg-type]
        valid_3m_count=int(payload["valid_3m_count"]),  # type: ignore[arg-type]
        ebitda_12m_count=int(payload["ebitda_12m_count"]),  # type: ignore[arg-type]
        duplicate_count=int(payload["duplicate_count"]),  # type: ignore[arg-type]
        invalid_count=int(payload["invalid_count"]),  # type: ignore[arg-type]
        records=recs,
    )


class MarketDataManager:
    """Manager for loading and caching ``MarketDataset`` with mtime/size invalidation."""

    def __init__(self, cache_root: Path | None = None) -> None:
        base = Path(__file__).resolve().parents[3]
        self.cache_root = cache_root or (base / ".cache")
        self._mem_cache: dict[tuple[str, str], MarketDataset] = {}

    def load(self, data_dir: Path | str, *, force_rebuild: bool = False) -> MarketDataset:
        folder = Path(data_dir).resolve()
        if not folder.is_dir():
            raise FileNotFoundError(f"Data directory not found: {folder}")

        fingerprint = _directory_fingerprint(folder)
        mem_key = (str(folder), fingerprint)
        if not force_rebuild and mem_key in self._mem_cache:
            return self._mem_cache[mem_key]

        cache_dir = self.cache_root / hashlib.sha256(str(folder).encode("utf-8")).hexdigest()[:12]
        manifest_path = cache_dir / "manifest.json"
        audit_path = cache_dir / "audit.json"
        ords_path = cache_dir / "ordinals.npy"
        prices_path = cache_dir / "prices.npy"
        ev_path = cache_dir / "ev.npy"
        fund_path = cache_dir / "fundamentals.parquet"
        meta_path = cache_dir / "assets_meta.parquet"

        if (
            not force_rebuild
            and manifest_path.is_file()
            and audit_path.is_file()
            and ords_path.is_file()
            and prices_path.is_file()
            and ev_path.is_file()
            and fund_path.is_file()
            and meta_path.is_file()
        ):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest.get("fingerprint") == fingerprint:
                    audit = _deserialize_audit(json.loads(audit_path.read_text(encoding="utf-8")))
                    all_ordinals = np.load(ords_path)
                    price_mat = np.load(prices_path)
                    ev_mat = np.load(ev_path)
                    fundamentals_df = pd.read_parquet(fund_path)
                    assets_meta_df = pd.read_parquet(meta_path)
                    tickers = list(manifest["tickers"])
                    dataset = _build_runtime_dataset(
                        folder,
                        audit,
                        all_ordinals,
                        tickers,
                        price_mat,
                        ev_mat,
                        fundamentals_df,
                        assets_meta_df,
                    )
                    self._mem_cache.clear()
                    self._mem_cache[mem_key] = dataset
                    return dataset
            except Exception:  # noqa: BLE001
                pass

        audit = audit_directory(folder)
        valid_records = [
            r for r in audit.records if r.category in {"valid_3m", "ebitda_12m"}
        ]
        if not valid_records:
            raise ValueError(f"Nenhum arquivo .xlsx valido encontrado em {folder}")

        worker_inputs = [(r.path, r.ebitda_window_months) for r in valid_records]
        n_workers = min(os.cpu_count() or 4, 8)
        if len(worker_inputs) < 20:
            parsed_items = [_parse_worker(item) for item in worker_inputs]
        else:
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                parsed_items = list(pool.map(_parse_worker, worker_inputs, chunksize=24))

        valid_items = [item for item in parsed_items if item is not None]
        if not valid_items:
            raise ValueError(f"Falha ao extrair series temporais dos arquivos em {folder}")

        valid_items.sort(key=lambda x: str(x["ticker"]))
        tickers = [str(x["ticker"]) for x in valid_items]

        all_ordinals = np.unique(
            np.concatenate([x["ordinals"] for x in valid_items])  # type: ignore[arg-type]
        )
        n_dates = len(all_ordinals)
        n_tickers = len(tickers)

        price_mat = np.full((n_dates, n_tickers), np.nan, dtype=np.float64)
        ev_mat = np.full((n_dates, n_tickers), np.nan, dtype=np.float64)

        fund_tickers: list[np.ndarray] = []
        fund_ords: list[np.ndarray] = []
        fund_eb_raw: list[np.ndarray] = []
        fund_eb_ltm: list[np.ndarray] = []
        fund_roics: list[np.ndarray] = []
        meta_rows: list[dict[str, object]] = []

        for col_idx, item in enumerate(valid_items):
            ords: np.ndarray = item["ordinals"]  # type: ignore[assignment]
            row_idx = np.searchsorted(all_ordinals, ords)
            price_mat[row_idx, col_idx] = item["prices"]  # type: ignore[index]
            ev_mat[row_idx, col_idx] = item["evs"]  # type: ignore[index]

            f_ords: np.ndarray = item["fund_ordinals"]  # type: ignore[assignment]
            if len(f_ords) > 0:
                fund_tickers.append(np.full(len(f_ords), item["ticker"], dtype=object))
                fund_ords.append(f_ords)
                fund_eb_raw.append(item["fund_ebitda_raw"])  # type: ignore[arg-type]
                fund_eb_ltm.append(item["fund_ebitda_ltm"])  # type: ignore[arg-type]
                fund_roics.append(item["fund_roic"])  # type: ignore[arg-type]

            first_ord = int(item["first_price_ord"])  # type: ignore[arg-type]
            last_ord = int(item["last_price_ord"])  # type: ignore[arg-type]
            meta_rows.append(
                {
                    "ticker": item["ticker"],
                    "company_name": item["company_name"],
                    "issuer": item["issuer"],
                    "filename": item["filename"],
                    "ebitda_window_months": item["ebitda_window_months"],
                    "first_price_date": date.fromordinal(first_ord).isoformat() if first_ord else None,
                    "last_price_date": date.fromordinal(last_ord).isoformat() if last_ord else None,
                    "trading_days_count": item["trading_days_count"],
                    "fundamentals_count": item["fundamentals_count"],
                }
            )

        assets_meta_df = pd.DataFrame(meta_rows)

        if fund_ords:
            fundamentals_df = pd.DataFrame(
                {
                    "ordinal": np.concatenate(fund_ords),
                    "ticker": np.concatenate(fund_tickers),
                    "ebitda_raw": np.concatenate(fund_eb_raw),
                    "ebitda_ltm": np.concatenate(fund_eb_ltm),
                    "roic": np.concatenate(fund_roics),
                }
            )
        else:
            fundamentals_df = pd.DataFrame(
                columns=["ordinal", "ticker", "ebitda_raw", "ebitda_ltm", "roic"]
            )

        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(ords_path, all_ordinals)
            np.save(prices_path, price_mat)
            np.save(ev_path, ev_mat)
            fundamentals_df.to_parquet(fund_path, compression="snappy", index=False)
            assets_meta_df.to_parquet(meta_path, compression="snappy", index=False)
            audit_path.write_text(
                json.dumps(_serialize_audit(audit), ensure_ascii=False),
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema": CACHE_SCHEMA_VERSION,
                        "fingerprint": fingerprint,
                        "total_tickers": n_tickers,
                        "total_dates": n_dates,
                        "tickers": tickers,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:  # noqa: BLE001
            pass

        dataset = _build_runtime_dataset(
            folder,
            audit,
            all_ordinals,
            tickers,
            price_mat,
            ev_mat,
            fundamentals_df,
            assets_meta_df,
        )
        self._mem_cache.clear()
        self._mem_cache[mem_key] = dataset
        return dataset


default_data_manager = MarketDataManager()
