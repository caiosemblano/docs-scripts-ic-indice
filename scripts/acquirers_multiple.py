"""Acquirer's Multiple ranking from per-asset Excel files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from common import (
    RankingResult,
    equal_weight,
    load_universe,
    parse_args_or_prompt,
    table_to_portfolio,
)


def _as_of_date(as_of: date | str) -> date:
    if isinstance(as_of, str):
        return date.fromisoformat(as_of)
    return as_of


def acquirers_multiple_table(
    data_dir: Path | str,
    as_of: date | str,
    n: int,
    *,
    warnings: list[str] | None = None,
) -> RankingResult:
    """Rank assets by EBITDA/EV and return the equal-weighted top N as a table."""
    as_of = _as_of_date(as_of)
    universe = load_universe(
        Path(data_dir),
        as_of,
        require_roic=False,
        warnings=warnings,
    ).copy()
    universe["nota"] = universe["EBITDA"] / universe["EV"]
    ranked = universe.sort_values(["nota", "ativo"], ascending=[False, True])
    selected = ranked.head(n).copy()
    empty = pd.DataFrame(columns=["posicao", "ativo", "EBITDA", "EV", "nota", "peso"])
    if selected.empty:
        return RankingResult(table=empty, n_valid=len(universe))

    selected.insert(0, "posicao", range(1, len(selected) + 1))
    selected["peso"] = equal_weight(len(selected))
    table = selected[["posicao", "ativo", "EBITDA", "EV", "nota", "peso"]].reset_index(drop=True)
    return RankingResult(table=table, n_valid=len(universe))


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
    return table_to_portfolio(acquirers_multiple_table(data_dir, as_of, n).table)


def main() -> None:
    data_dir, as_of, n = parse_args_or_prompt("Acquirer's Multiple portfolio ranking")
    portfolio = rank_acquirers_multiple(data_dir, as_of, n)
    print(portfolio)


if __name__ == "__main__":
    main()
