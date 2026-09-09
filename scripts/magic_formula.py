"""Magic Formula ranking from per-asset Excel files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from common import load_universe, parse_args_or_prompt, to_portfolio


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
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    universe = load_universe(Path(data_dir), as_of, require_roic=True)
    universe = universe.copy()
    universe["earnings_yield"] = universe["EBITDA"] / universe["EV"]
    universe["rank_yield"] = universe["earnings_yield"].rank(ascending=False, method="average")
    universe["rank_roic"] = universe["ROIC"].rank(ascending=False, method="average")
    universe["nota"] = universe["rank_yield"] + universe["rank_roic"]
    ranked = (
        universe.sort_values(["nota", "ativo"], ascending=[True, True])[["ativo", "nota"]]
        .itertuples(index=False, name=None)
    )
    return to_portfolio(ranked, n)


def main() -> None:
    data_dir, as_of, n = parse_args_or_prompt("Magic Formula portfolio ranking")
    portfolio = rank_magic_formula(data_dir, as_of, n)
    print(portfolio)


if __name__ == "__main__":
    main()
