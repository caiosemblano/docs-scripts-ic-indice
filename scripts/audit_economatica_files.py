"""Audit and separate Economatica .xlsx files in data/ (or dados/).

Identifies:
1. Files exported with ``EBITDA ... de 12 meses`` instead of ``de 3 meses`` (so they can be re-exported cleanly).
2. Duplicate files (e.g. ``(1).xlsx``, ``OLD.xlsx``, or duplicate sheet tickers).
3. Non-Economatica / invalid spreadsheets missing ``Date``, ``EBITDA``, or ``EV``.

Usage:
    # Dry-run audit + CSV reports (default)
    python scripts/audit_economatica_files.py --data-dir ./data

    # Physically separate 12m, duplicate, and invalid files into sibling folders
    python scripts/audit_economatica_files.py --data-dir ./data --move
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.app.core.economatica_xml import XlsxAuditInfo, inspect_xlsx_header  # noqa: E402


@dataclass(slots=True)
class AuditRecord:
    filename: str
    ticker: str
    company_name: str
    category: str  # "valid_3m" | "ebitda_12m" | "duplicate" | "invalid"
    ebitda_window_months: int | None
    raw_ebitda_header: str
    columns_detected: str
    reason: str
    path: str


@dataclass(slots=True)
class DatasetAuditResult:
    data_dir: str
    total_files: int
    valid_3m_count: int
    ebitda_12m_count: int
    duplicate_count: int
    invalid_count: int
    records: list[AuditRecord]

    @property
    def ebitda_12m_records(self) -> list[AuditRecord]:
        return [r for r in self.records if r.category == "ebitda_12m"]

    @property
    def duplicate_records(self) -> list[AuditRecord]:
        return [r for r in self.records if r.category == "duplicate"]

    @property
    def invalid_records(self) -> list[AuditRecord]:
        return [r for r in self.records if r.category == "invalid"]


def resolve_default_data_dir(explicit: Path | str | None = None) -> Path:
    """Resolve data directory, preferring explicit path, then ./data, then ./dados."""
    if explicit is not None:
        return Path(explicit)
    for candidate_name in ("data", "dados"):
        candidate = ROOT_DIR / candidate_name
        if candidate.is_dir() and any(candidate.glob("*.xlsx")):
            return candidate
    for candidate_name in ("data", "dados"):
        candidate = ROOT_DIR / candidate_name
        if candidate.is_dir():
            return candidate
    return ROOT_DIR / "dados"


def audit_directory(data_dir: Path | str) -> DatasetAuditResult:
    """Inspect all ``*.xlsx`` files in ``data_dir`` and classify anomalies."""
    folder = Path(data_dir)
    paths = sorted(
        p for p in folder.glob("*.xlsx") if not p.name.startswith("~$")
    )

    if not paths:
        return DatasetAuditResult(
            data_dir=str(folder),
            total_files=0,
            valid_3m_count=0,
            ebitda_12m_count=0,
            duplicate_count=0,
            invalid_count=0,
            records=[],
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        inspected: list[XlsxAuditInfo] = list(pool.map(inspect_xlsx_header, paths))

    # Order non-copy filenames first so clean files win primary ticker ownership
    ordered_for_dedup = sorted(
        inspected,
        key=lambda info: (
            1 if info.is_copy_filename else 0,
            len(info.filename),
            info.filename,
        ),
    )

    seen_tickers: dict[str, str] = {}
    categorized_by_name: dict[str, AuditRecord] = {}

    for info in ordered_for_dedup:
        cols = set(info.columns_detected)
        if info.error or info.header_row is None or not {"Date", "EBITDA", "EV"}.issubset(cols):
            reason = info.error or (
                f"Colunas obrigatorias ausentes (encontradas: {list(info.columns_detected)})"
            )
            categorized_by_name[info.filename] = AuditRecord(
                filename=info.filename,
                ticker=info.ticker,
                company_name=info.company_name,
                category="invalid",
                ebitda_window_months=info.ebitda_window_months,
                raw_ebitda_header=info.raw_ebitda_header,
                columns_detected=",".join(info.columns_detected),
                reason=reason,
                path=str(info.path),
            )
            continue

        if info.ticker in seen_tickers:
            primary_file = seen_tickers[info.ticker]
            categorized_by_name[info.filename] = AuditRecord(
                filename=info.filename,
                ticker=info.ticker,
                company_name=info.company_name,
                category="duplicate",
                ebitda_window_months=info.ebitda_window_months,
                raw_ebitda_header=info.raw_ebitda_header,
                columns_detected=",".join(info.columns_detected),
                reason=f"Ticker '{info.ticker}' duplicado (principal: {primary_file})",
                path=str(info.path),
            )
            continue

        seen_tickers[info.ticker] = info.filename

        if info.ebitda_window_months == 12:
            categorized_by_name[info.filename] = AuditRecord(
                filename=info.filename,
                ticker=info.ticker,
                company_name=info.company_name,
                category="ebitda_12m",
                ebitda_window_months=12,
                raw_ebitda_header=info.raw_ebitda_header,
                columns_detected=",".join(info.columns_detected),
                reason="EBITDA exportado com janela 'de 12 meses' em vez de 'de 3 meses'",
                path=str(info.path),
            )
        else:
            categorized_by_name[info.filename] = AuditRecord(
                filename=info.filename,
                ticker=info.ticker,
                company_name=info.company_name,
                category="valid_3m",
                ebitda_window_months=info.ebitda_window_months or 3,
                raw_ebitda_header=info.raw_ebitda_header,
                columns_detected=",".join(info.columns_detected),
                reason="OK",
                path=str(info.path),
            )

    records = [categorized_by_name[p.name] for p in paths]
    return DatasetAuditResult(
        data_dir=str(folder),
        total_files=len(records),
        valid_3m_count=sum(1 for r in records if r.category == "valid_3m"),
        ebitda_12m_count=sum(1 for r in records if r.category == "ebitda_12m"),
        duplicate_count=sum(1 for r in records if r.category == "duplicate"),
        invalid_count=sum(1 for r in records if r.category == "invalid"),
        records=records,
    )


def write_audit_csvs(result: DatasetAuditResult, report_dir: Path) -> tuple[Path, Path]:
    """Export full audit CSV and dedicated 12-month EBITDA re-export CSV."""
    report_dir.mkdir(parents=True, exist_ok=True)
    full_csv = report_dir / "economatica_audit_completo.csv"
    reexport_csv = report_dir / "reexportar_ebitda_12m.csv"

    fieldnames = [
        "filename",
        "ticker",
        "company_name",
        "category",
        "ebitda_window_months",
        "raw_ebitda_header",
        "columns_detected",
        "reason",
    ]

    with full_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for rec in result.records:
            row = asdict(rec)
            row.pop("path", None)
            writer.writerow(row)

    with reexport_csv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=["ticker", "company_name", "filename", "raw_ebitda_header", "reason"],
        )
        writer.writeheader()
        for rec in result.ebitda_12m_records:
            writer.writerow(
                {
                    "ticker": rec.ticker,
                    "company_name": rec.company_name,
                    "filename": rec.filename,
                    "raw_ebitda_header": rec.raw_ebitda_header,
                    "reason": rec.reason,
                }
            )

    return full_csv, reexport_csv


def separate_files(
    result: DatasetAuditResult,
    *,
    out_12m_dir: Path,
    out_dup_dir: Path,
    out_invalid_dir: Path,
    copy_only: bool = False,
) -> dict[str, int]:
    """Move (or copy) divergent files out of data_dir into dedicated folders."""
    counts = {"ebitda_12m": 0, "duplicate": 0, "invalid": 0}
    target_map = {
        "ebitda_12m": out_12m_dir,
        "duplicate": out_dup_dir,
        "invalid": out_invalid_dir,
    }

    for rec in result.records:
        dest_dir = target_map.get(rec.category)
        if dest_dir is None:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        src = Path(rec.path)
        dst = dest_dir / src.name
        if copy_only:
            shutil.copy2(src, dst)
        else:
            shutil.move(str(src), str(dst))
        counts[rec.category] += 1

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audita e separa planilhas Economatica com EBITDA de 12 meses, duplicadas ou invalidas."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Pasta com os arquivos .xlsx (padrao: ./data se existir, senao ./dados)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT_DIR / "audit_reports",
        help="Pasta onde salvar os CSVs de auditoria e lista de re-exportacao",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Nao gravar arquivos CSV de auditoria",
    )
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--move",
        action="store_true",
        help="Move fisicamente os arquivos de 12 meses, duplicados e invalidos para pastas separadas",
    )
    action_group.add_argument(
        "--copy-12m",
        action="store_true",
        help="Copia os arquivos divergentes para pastas separadas sem remover de data/",
    )
    parser.add_argument(
        "--out-12m-dir",
        type=Path,
        default=None,
        help="Pasta de destino para arquivos com EBITDA de 12 meses (padrao: <pai>/data_reexportar_12m)",
    )
    args = parser.parse_args()

    data_dir = resolve_default_data_dir(args.data_dir)
    if not data_dir.is_dir():
        raise SystemExit(f"Diretorio de dados nao encontrado: {data_dir}")

    result = audit_directory(data_dir)
    print(f"=== Auditoria Economatica: {result.data_dir} ===")
    print(f"Total de arquivos .xlsx : {result.total_files}")
    print(f"  Validos (EBITDA 3m)   : {result.valid_3m_count}")
    print(f"  EBITDA de 12 meses    : {result.ebitda_12m_count}")
    print(f"  Duplicados            : {result.duplicate_count}")
    print(f"  Invalidos / Outros    : {result.invalid_count}")

    if result.ebitda_12m_records:
        print(f"\n--- Arquivos com EBITDA de 12 meses ({len(result.ebitda_12m_records)}) ---")
        for rec in result.ebitda_12m_records:
            print(f"  [{rec.ticker:<10}] {rec.filename:<38} ({rec.company_name})")

    if result.duplicate_records:
        print(f"\n--- Arquivos Duplicados ({len(result.duplicate_records)}) ---")
        for rec in result.duplicate_records:
            print(f"  [{rec.ticker:<10}] {rec.filename:<38} -> {rec.reason}")

    if result.invalid_records:
        print(f"\n--- Arquivos Invalidos / Fora do Padrao ({len(result.invalid_records)}) ---")
        for rec in result.invalid_records:
            print(f"  {rec.filename:<42} -> {rec.reason}")

    if not args.no_report and result.total_files > 0:
        full_csv, reexport_csv = write_audit_csvs(result, args.report_dir)
        print(f"\nRelatorios gerados:")
        print(f"  - Lista para re-exportar (12m): {reexport_csv}")
        print(f"  - Auditoria completa          : {full_csv}")

    if args.move or args.copy_12m:
        parent = data_dir.resolve().parent
        out_12m = args.out_12m_dir or (parent / "data_reexportar_12m")
        out_dup = parent / "data_duplicados"
        out_inv = parent / "data_invalidos"
        counts = separate_files(
            result,
            out_12m_dir=out_12m,
            out_dup_dir=out_dup,
            out_invalid_dir=out_inv,
            copy_only=args.copy_12m,
        )
        verb = "Copiados" if args.copy_12m else "Movidos"
        print(f"\n{verb} com sucesso:")
        print(f"  - EBITDA 12m ({counts['ebitda_12m']}) -> {out_12m}")
        print(f"  - Duplicados ({counts['duplicate']}) -> {out_dup}")
        print(f"  - Invalidos  ({counts['invalid']}) -> {out_inv}")
    else:
        print(
            "\nDica: rode com `--move` para mover automaticamente esses arquivos para pastas separadas "
            "ou `--copy-12m` para copia-los sem alterar a pasta original."
        )


if __name__ == "__main__":
    main()
