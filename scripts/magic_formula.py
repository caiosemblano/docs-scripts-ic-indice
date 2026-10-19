"""Magic Formula ranking from per-asset Excel files."""

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


def magic_formula_table(
    data_dir: Path | str,
    start_date: date | str,
    years: int,
    n: int,
    *,
    warnings: list[str] | None = None,
) -> RankingResult:
    """Rank assets by combined EY + ROIC ranks inside a year window."""
    start_date = _coerce_date(start_date)
    universe = load_universe(
        Path(data_dir),
        start_date,
        years,
        require_roic=True,
        warnings=warnings,
    ).copy()
    universe["earnings_yield"] = universe["EBITDA"] / universe["EV"]
    universe["rank_yield"] = universe["earnings_yield"].rank(ascending=False, method="average")
    universe["rank_roic"] = universe["ROIC"].rank(ascending=False, method="average")
    universe["nota"] = universe["rank_yield"] + universe["rank_roic"]
    ranked = universe.sort_values(["nota", "ativo"], ascending=[True, True])
    selected = ranked.head(n).copy()
    empty = pd.DataFrame(columns=["posicao", "ativo", "EBITDA", "EV", "ROIC", "nota", "peso"])
    if selected.empty:
        return RankingResult(table=empty, n_valid=len(universe))

    selected.insert(0, "posicao", range(1, len(selected) + 1))
    selected["peso"] = score_weights(selected["nota"], higher_is_better=False)
    table = selected[["posicao", "ativo", "EBITDA", "EV", "ROIC", "nota", "peso"]].reset_index(
        drop=True,
    )
    return RankingResult(table=table, n_valid=len(universe))


def rank_magic_formula(
    data_dir: Path | str,
    start_date: date | str,
    years: int,
    n: int,
) -> list[tuple[str, float, float]]:
    """Rank assets by combined EY + ROIC ranks (lower combined rank is better).

    Metrics come from the latest valid row in ``[start_date, start_date + years]``.

    Returns
    -------
    list[tuple[str, float, float]]
        (asset_name, combined_rank_nota, weight proportional to 1/nota)
    """
    return table_to_portfolio(
        magic_formula_table(data_dir, start_date, years, n).table,
    )


def main() -> None:
    data_dir, start_date, years, n = parse_args_or_prompt("Magic Formula portfolio ranking")
    portfolio = rank_magic_formula(data_dir, start_date, years, n)
    print(portfolio)


if __name__ == "__main__":
    main()
