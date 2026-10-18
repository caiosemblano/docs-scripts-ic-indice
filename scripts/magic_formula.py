"""Magic Formula ranking from per-asset Excel files."""

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


def magic_formula_table(
    data_dir: Path | str,
    as_of: date | str,
    n: int,
    *,
    warnings: list[str] | None = None,
) -> RankingResult:
    """Rank assets by combined EY + ROIC ranks and return the top N as a table."""
    as_of = _as_of_date(as_of)
    universe = load_universe(
        Path(data_dir),
        as_of,
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
    selected["peso"] = equal_weight(len(selected))
    table = selected[["posicao", "ativo", "EBITDA", "EV", "ROIC", "nota", "peso"]].reset_index(
        drop=True,
    )
    return RankingResult(table=table, n_valid=len(universe))


def rank_magic_formula(
    data_dir: Path | str,
    as_of: date | str,
    n: int,
) -> list[tuple[str, float, float]]:
    """Rank assets by combined EY + ROIC ranks (lower combined rank is better).

    Returns
    -------
    list[tuple[str, float, float]]
        (asset_name, combined_rank_nota, weight)
    """
    return table_to_portfolio(magic_formula_table(data_dir, as_of, n).table)


def main() -> None:
    data_dir, as_of, n = parse_args_or_prompt("Magic Formula portfolio ranking")
    portfolio = rank_magic_formula(data_dir, as_of, n)
    print(portfolio)


if __name__ == "__main__":
    main()
