"""Acquirer's Multiple ranking from per-asset Excel files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from common import (
    RankingResult,
    load_universe,
    parse_args_or_prompt,
    score_weights,
    table_to_portfolio,
)


def _coerce_date(value: date | str) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


def acquirers_multiple_table(
    data_dir: Path | str,
    start_date: date | str,
    years: int,
    n: int,
    *,
    warnings: list[str] | None = None,
) -> RankingResult:
    """Rank assets by EBITDA/EV using the latest metrics in the year window."""
    start_date = _coerce_date(start_date)
    universe = load_universe(
        Path(data_dir),
        start_date,
        years,
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
    selected["peso"] = score_weights(selected["nota"], higher_is_better=True)
    table = selected[["posicao", "ativo", "EBITDA", "EV", "nota", "peso"]].reset_index(drop=True)
    return RankingResult(table=table, n_valid=len(universe))


def rank_acquirers_multiple(
    data_dir: Path | str,
    start_date: date | str,
    years: int,
    n: int,
) -> list[tuple[str, float, float]]:
    """Rank assets by EBITDA/EV (higher is better) and return score-weighted top N.

    Metrics come from the latest valid row in ``[start_date, start_date + years]``.

    Returns
    -------
    list[tuple[str, float, float]]
        (asset_name, earnings_yield_nota, weight proportional to nota)
    """
    return table_to_portfolio(
        acquirers_multiple_table(data_dir, start_date, years, n).table,
    )


def main() -> None:
    data_dir, start_date, years, n = parse_args_or_prompt(
        "Acquirer's Multiple portfolio ranking",
    )
    portfolio = rank_acquirers_multiple(data_dir, start_date, years, n)
    print(portfolio)


if __name__ == "__main__":
    main()
