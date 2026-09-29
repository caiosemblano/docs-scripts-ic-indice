"""Acquirer's Multiple ranking from per-asset Excel files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from common import load_universe, parse_args_or_prompt, to_portfolio


def rank_from_universe(universe: pd.DataFrame, n: int) -> list[tuple[str, float, float]]:
    """Rank a ready universe by EBITDA/EV (higher is better)."""
    ranked_df = universe.copy()
    ranked_df["nota"] = ranked_df["EBITDA"] / ranked_df["EV"]
    ranked = (
        ranked_df.sort_values(["nota", "ativo"], ascending=[False, True])[["ativo", "nota"]]
        .itertuples(index=False, name=None)
    )
    return to_portfolio(ranked, n)


def rank_acquirers_multiple(
    data_dir: Path | str,
    as_of: date | str,
    n: int,
) -> list[tuple[str, float, float]]:
    """Rank assets by EBITDA/EV (higher is better) and return equal-weighted top N.

    Returns
    -------
    list[tuple[str, float, float]]
        (asset_name, earnings_yield_nota, weight)
    """
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    universe = load_universe(Path(data_dir), as_of, require_roic=False)
    return rank_from_universe(universe, n)


def main() -> None:
    data_dir, as_of, n = parse_args_or_prompt("Acquirer's Multiple portfolio ranking")
    portfolio = rank_acquirers_multiple(data_dir, as_of, n)
    print(portfolio)


if __name__ == "__main__":
    main()
