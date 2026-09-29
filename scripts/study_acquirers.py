"""Historical-window study for the Acquirer's Multiple portfolio."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from acquirers_multiple import rank_from_universe
from common import (
    holding_period_return,
    load_panel,
    rebalance_dates,
    turnover,
    universe_as_of,
)


def _resolve_data_dir(raw: Path | None, default: str = "./dados") -> Path:
    data_dir = raw if raw is not None else Path(default)
    if not data_dir.is_dir():
        raise SystemExit(f"Data directory not found: {data_dir}")
    return data_dir


def run_study(
    data_dir: Path,
    start: date | None,
    end: date | None,
    freq: str,
    n: int,
    max_age_days: int | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = load_panel(data_dir, require_roic=False)
    has_price = "Close" in panel.columns and bool(panel["Close"].notna().any())
    if start is None:
        start = min(panel["Date"])
    if end is None:
        end = max(panel["Date"])

    windows: list[tuple[date, list[tuple[str, float, float]]]] = []
    for as_of in rebalance_dates(start, end, freq):
        try:
            universe = universe_as_of(panel, as_of, max_age_days=max_age_days)
        except ValueError as exc:
            print(f"Warning: {exc}; skipped {as_of.isoformat()}", file=sys.stderr)
            continue
        portfolio = rank_from_universe(universe, n)
        if not portfolio:
            print(f"Warning: empty portfolio on {as_of.isoformat()}; skipped", file=sys.stderr)
            continue
        windows.append((as_of, portfolio))

    if not windows:
        raise SystemExit("No rebalance windows produced a portfolio")

    holdings_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    nav = 1000.0
    previous_weights: dict[str, float] = {}

    for index, (as_of, portfolio) in enumerate(windows):
        weights = {name: weight for name, _nota, weight in portfolio}
        period_ret: float | None = None
        if has_price and index + 1 < len(windows):
            period_ret = holding_period_return(panel, portfolio, as_of, windows[index + 1][0])

        for position, (name, nota, weight) in enumerate(portfolio, start=1):
            holdings_rows.append(
                {
                    "rebalance": as_of.isoformat(),
                    "rank": position,
                    "ativo": name,
                    "nota": nota,
                    "peso": weight,
                }
            )

        summary_rows.append(
            {
                "rebalance": as_of.isoformat(),
                "n": len(portfolio),
                "turnover": 0.0 if not previous_weights else turnover(previous_weights, weights),
                "holding_return": period_ret,
                "nav": nav if has_price else None,
            }
        )
        if period_ret is not None:
            nav *= 1.0 + period_ret
        previous_weights = weights

    return pd.DataFrame(holdings_rows), pd.DataFrame(summary_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Walk-forward Acquirer's Multiple study over historical windows",
    )
    parser.add_argument("--data-dir", type=Path, default=None, help="Directory with one .xlsx per asset")
    parser.add_argument("--start", type=str, default=None, help="First window YYYY-MM-DD (default: min date)")
    parser.add_argument("--end", type=str, default=None, help="Last window YYYY-MM-DD (default: max date)")
    parser.add_argument(
        "--freq",
        choices=("M", "Q", "Y"),
        default="M",
        help="Rebalance frequency: month (M), quarter (Q) or year (Y)",
    )
    parser.add_argument("--n", type=int, default=30, help="Portfolio size (default: 30)")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Drop fundamentals older than this many days at rebalance",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="If set, write holdings.csv and summary.csv here",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.n <= 0:
        raise SystemExit("Portfolio size --n must be a positive integer")

    data_dir = _resolve_data_dir(args.data_dir)
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None

    holdings, summary = run_study(
        data_dir=data_dir,
        start=start,
        end=end,
        freq=args.freq,
        n=args.n,
        max_age_days=args.max_age_days,
    )

    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        holdings_path = args.out_dir / "holdings.csv"
        summary_path = args.out_dir / "summary.csv"
        holdings.to_csv(holdings_path, index=False)
        summary.to_csv(summary_path, index=False)
        print(f"Wrote {holdings_path}")
        print(f"Wrote {summary_path}")

    with pd.option_context("display.max_rows", 50, "display.width", 120):
        print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
