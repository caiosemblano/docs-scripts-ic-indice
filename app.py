"""Streamlit UI for Acquirer's Multiple and Magic Formula portfolio ranking."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from acquirers_multiple import acquirers_multiple_table  # noqa: E402
from common import add_years, inspect_data_dir  # noqa: E402
from magic_formula import magic_formula_table  # noqa: E402

STRATEGY_ACQUIRERS = "Acquirer's Multiple"
STRATEGY_MAGIC = "Magic Formula"
STRATEGY_BOTH = "Comparar ambas"
DEFAULT_DATA_DIR = "./dados"
# Bump when ranking or weighting logic changes so @st.cache_data discards stale tables.
RANKING_LOGIC_VERSION = 3
COLUMN_LABELS = {
    "posicao": "Posição",
    "ativo": "Ativo",
    "EBITDA": "EBITDA",
    "EV": "EV",
    "ROIC": "ROIC",
    "nota": "Nota",
    "peso": "Peso",
}


def discover_data_dirs(root: Path) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        if not path.is_dir():
            return
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(path)

    add(root / "dados")
    try:
        children = sorted(root.iterdir())
    except OSError:
        children = []
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir() and any(child.glob("*.xlsx")):
            add(child)
    if any(root.glob("*.xlsx")):
        add(root)
    return found


def dir_signature(data_dir: Path) -> str:
    parts: list[str] = []
    try:
        paths = sorted(data_dir.glob("*.xlsx"))
    except OSError:
        return ""
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        parts.append(f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}")
    return "|".join(parts)


@st.cache_data(show_spinner="Lendo arquivos do diretório...")
def cached_inspect(data_dir: str, signature: str) -> tuple[list[str], list[date]]:
    del signature
    paths, dates = inspect_data_dir(Path(data_dir))
    return [str(path) for path in paths], dates


@st.cache_data(show_spinner="Calculando ranking...")
def run_ranking(
    strategy: str,
    data_dir: str,
    start_date: str,
    years: int,
    n: int,
    signature: str,
    logic_version: int,
) -> tuple[pd.DataFrame, int, list[str]]:
    del signature, logic_version
    warnings: list[str] = []
    if strategy == STRATEGY_MAGIC:
        result = magic_formula_table(
            data_dir,
            start_date,
            years,
            n,
            warnings=warnings,
        )
    else:
        result = acquirers_multiple_table(
            data_dir,
            start_date,
            years,
            n,
            warnings=warnings,
        )
    return result.table, result.n_valid, warnings


def format_table(table: pd.DataFrame) -> pd.DataFrame:
    display = table.rename(columns=COLUMN_LABELS)
    return display


def render_warnings(warnings: list[str]) -> None:
    with st.expander(f"Diagnóstico de dados ({len(warnings)} aviso(s))", expanded=False):
        if not warnings:
            st.caption("Nenhum ativo foi descartado nesta data.")
            return
        st.caption("Ativos ignorados e o motivo correspondente:")
        for message in warnings:
            st.text(f"- {message.removeprefix('Warning: ')}")


def render_portfolio(
    title: str,
    table: pd.DataFrame,
    n_valid: int,
    warnings: list[str],
    start_date: date,
    years: int,
    end_date: date,
    n_files: int,
    slug: str,
) -> None:
    st.subheader(title)
    st.caption(
        f"Janela {start_date.isoformat()} a {end_date.isoformat()} ({years} ano(s)). "
        "Cada ativo usa o último EBITDA, EV e ROIC válidos dentro desse intervalo."
    )
    selected = len(table)
    max_weight = float(table["peso"].max()) if selected else 0.0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Arquivos .xlsx", n_files)
    c2.metric("Ativos válidos", n_valid)
    c3.metric("Selecionados (n)", selected)
    c4.metric("Maior peso", f"{max_weight:.2%}")

    if table.empty:
        st.info("Nenhum ativo selecionado para os parâmetros atuais.")
        render_warnings(warnings)
        return

    st.dataframe(
        format_table(table),
        hide_index=True,
        width="stretch",
        column_config={
            "Posição": st.column_config.NumberColumn(format="%d"),
            "Nota": st.column_config.NumberColumn(format="%.6f"),
            "Peso": st.column_config.NumberColumn(format="percent"),
            "ROIC": st.column_config.NumberColumn(format="%.4f"),
        },
    )
    csv_bytes = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Baixar carteira (CSV)",
        data=csv_bytes,
        file_name=f"carteira_{slug}_{start_date.isoformat()}_{years}anos.csv",
        mime="text/csv",
        key=f"download_{slug}_{start_date.isoformat()}_{years}",
    )
    render_warnings(warnings)


def main() -> None:
    st.set_page_config(page_title="Ranking de carteiras", layout="wide")
    st.title("Ranking de carteiras")
    st.caption(
        "Monte uma carteira ponderada pela nota a partir de planilhas Excel "
        "(Acquirer's Multiple ou Magic Formula), usando o último dado válido "
        "dentro de uma janela de anos."
    )

    with st.sidebar:
        st.header("Parâmetros")
        shortcuts = discover_data_dirs(ROOT)
        shortcut_labels = ["Personalizado"] + [
            str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)
            for path in shortcuts
        ]
        chosen = st.selectbox("Atalho de diretório", shortcut_labels)
        if chosen == "Personalizado":
            raw_dir = st.text_input("Diretório de dados", value=DEFAULT_DATA_DIR)
            data_dir = Path(raw_dir).expanduser()
        else:
            data_dir = ROOT / chosen if not Path(chosen).is_absolute() else Path(chosen)
            st.caption(f"Usando `{data_dir}`")

        strategy = st.radio(
            "Estratégia",
            [STRATEGY_ACQUIRERS, STRATEGY_MAGIC, STRATEGY_BOTH],
        )

    if not data_dir.is_dir():
        st.error(f"Diretório de dados não encontrado: {data_dir}")
        st.stop()

    try:
        paths, dates = cached_inspect(str(data_dir), dir_signature(data_dir))
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.stop()

    n_files = len(paths)
    min_date = dates[0] if dates else None
    max_date = dates[-1] if dates else None

    with st.sidebar:
        st.metric("Arquivos .xlsx detectados", n_files)
        st.subheader("Configuração temporal")
        start_date = st.date_input(
            "Data inicial",
            value=min_date or date.today(),
            min_value=min_date,
            max_value=max_date,
            key=f"start_{data_dir.resolve()}",
            help=(
                "Início da janela. O ranking usa o último EBITDA, EV e ROIC "
                "válidos entre esta data e a data inicial mais o período em anos. "
                "Observações anteriores à data inicial são ignoradas."
            ),
        )
        years = int(
            st.number_input(
                "Período da janela (anos)",
                min_value=1,
                value=1,
                step=1,
                key=f"years_{data_dir.resolve()}",
            )
        )
        if not isinstance(start_date, date):
            st.error("Selecione uma data inicial.")
            st.stop()
        end_date = add_years(start_date, years)
        st.date_input(
            "Data final da janela",
            value=end_date,
            disabled=True,
            key=f"end_{data_dir.resolve()}_{start_date.isoformat()}_{years}",
            help="Fim inclusivo da janela: data inicial mais o período em anos.",
        )
        max_n = max(1, n_files)
        n = int(
            st.number_input(
                "Número de ações na carteira (n)",
                min_value=1,
                max_value=max_n,
                value=min(30, max_n),
                step=1,
                key=f"n_{data_dir.resolve()}_{n_files}",
            )
        )

    if n_files == 0:
        st.warning(f"Nenhum arquivo `.xlsx` encontrado em `{data_dir}`.")
        st.stop()
    if not dates:
        st.warning("Nenhuma data válida foi encontrada nas planilhas deste diretório.")
        st.stop()

    signature = dir_signature(data_dir)
    start_iso = start_date.isoformat()
    strategies = (
        [STRATEGY_ACQUIRERS, STRATEGY_MAGIC] if strategy == STRATEGY_BOTH else [strategy]
    )

    slugs = {
        STRATEGY_ACQUIRERS: "acquirers-multiple",
        STRATEGY_MAGIC: "magic-formula",
    }

    if len(strategies) == 1:
        name = strategies[0]
        try:
            table, n_valid, warnings = run_ranking(
                name,
                str(data_dir),
                start_iso,
                years,
                n,
                signature,
                RANKING_LOGIC_VERSION,
            )
        except (FileNotFoundError, ValueError) as exc:
            st.error(str(exc))
            st.stop()
        render_portfolio(
            name,
            table,
            n_valid,
            warnings,
            start_date,
            years,
            end_date,
            n_files,
            slugs[name],
        )
        return

    left, right = st.columns(2)
    for column, name in zip((left, right), strategies, strict=True):
        with column:
            try:
                table, n_valid, warnings = run_ranking(
                    name,
                    str(data_dir),
                    start_iso,
                    years,
                    n,
                    signature,
                    RANKING_LOGIC_VERSION,
                )
            except (FileNotFoundError, ValueError) as exc:
                st.error(str(exc))
                continue
            render_portfolio(
                name,
                table,
                n_valid,
                warnings,
                start_date,
                years,
                end_date,
                n_files,
                slugs[name],
            )


if __name__ == "__main__":
    main()
