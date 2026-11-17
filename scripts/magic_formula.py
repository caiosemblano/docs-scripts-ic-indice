"""Magic Formula ranking from per-asset Excel files (Economatica & standard Excel)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
for p in (str(ROOT_DIR), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.app.core.data_loader import default_data_manager  # noqa: E402
from backend.app.core.ranking import rank_dataset_on_date  # noqa: E402
from common import parse_args_or_prompt  # noqa: E402


def rank_magic_formula(
    data_dir: Path | str,
    as_of: date | str,
    n: int,
    *,
    deduplicate_issuers: bool = True,
) -> list[tuple[str, float, float]]:
    """Rank assets by combined EY + ROIC ranks (lower combined rank is better)."""
    if isinstance(as_of, str):
        as_of = date.fromisoformat(as_of)
    folder = Path(data_dir)
    if not any(p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")):
        raise FileNotFoundError(f"No .xlsx files found in {folder}")

    dataset = default_data_manager.load(folder)
    require_price = len(dataset.trading_dates) > 0
    holdings = rank_dataset_on_date(
        dataset,
        as_of,
        "magic_formula",
        n,
        deduplicate_issuers=deduplicate_issuers,
        require_valid_price=require_price,
    )
    if not holdings:
        raise ValueError(f"No valid assets found for {as_of.isoformat()} in {folder}")
    return [(h.ticker, h.score, h.weight) for h in holdings]


def main() -> None:
    data_dir, as_of, n, dedup = parse_args_or_prompt("Magic Formula portfolio ranking")
    portfolio = rank_magic_formula(data_dir, as_of, n, deduplicate_issuers=dedup)
    print(portfolio)


if __name__ == "__main__":
    main()
