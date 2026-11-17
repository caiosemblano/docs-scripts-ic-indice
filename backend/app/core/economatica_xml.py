"""Ultra-fast streaming XML reader for Economatica and standard .xlsx files.

Uses C-accelerated ``xml.parsers.expat`` inside ``zipfile`` to avoid ``openpyxl``
object overhead when reading 2,000+ multi-decade spreadsheets.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
import xml.parsers.expat
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

EXCEL_EPOCH = datetime(1899, 12, 30)
MISSING_TOKENS = {"", "-", "--", "n/a", "na", "nan", "null", "none", "#n/a", "#valor!", "#div/0!", "#ref!"}
COPY_FILENAME_RE = re.compile(r"(?:\(\d+\)|\bOLD\b|\bCOPIA\b|\bCOPY\b)", re.IGNORECASE)


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def classify_column_header(raw_header: str) -> tuple[str | None, dict[str, Any]]:
    """Map an Economatica or standard column header to canonical column name and metadata.

    Canonical names: ``Date``, ``Price``, ``EBITDA``, ``EV``, ``ROIC``.
    """
    if not raw_header:
        return None, {}
    cleaned = _strip_accents(str(raw_header)).strip().lower()
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    first_line = lines[0] if lines else cleaned
    flat = " ".join(lines)

    if first_line in {"date", "data"} or flat in {"date", "data"}:
        return "Date", {}

    if (
        first_line in {"price", "close", "adj close", "adj_close", "preco", "cotacao", "fechamento"}
        or first_line.startswith("fechamento")
        or first_line.startswith("cotacao")
        or first_line.startswith("preco")
        or "adj close" in first_line
    ):
        return "Price", {}

    if first_line == "ebitda" or first_line.startswith("ebitda"):
        window_months: int | None = None
        if "12 meses" in flat or "12m" in flat or "ltm" in flat or "ttm" in flat:
            window_months = 12
        elif "3 meses" in flat or "3m" in flat or "trimestral" in flat:
            window_months = 3
        return "EBITDA", {"ebitda_window_months": window_months, "raw_ebitda_header": " | ".join(lines)}

    if first_line == "ev" or first_line.startswith("ev ") or first_line == "enterprise value":
        return "EV", {}

    if first_line == "roic" or first_line.startswith("roic"):
        return "ROIC", {}

    return None, {}


def _parse_shared_strings(xml_bytes: bytes) -> list[str]:
    """Parse ``xl/sharedStrings.xml`` quickly using C expat."""
    strings: list[str] = []
    current_parts: list[str] = []
    in_si = False
    in_t = False
    in_rph = False  # Ignore phonetic runs <rPh>

    def start_el(name: str, attrs: dict[str, str]) -> None:
        nonlocal in_si, in_t, in_rph
        local = name.rsplit(":", 1)[-1]
        if local == "si":
            in_si = True
            current_parts.clear()
        elif in_si and local == "rPh":
            in_rph = True
        elif in_si and not in_rph and local == "t":
            in_t = True

    def end_el(name: str) -> None:
        nonlocal in_si, in_t, in_rph
        local = name.rsplit(":", 1)[-1]
        if local == "t":
            in_t = False
        elif local == "rPh":
            in_rph = False
        elif local == "si":
            strings.append("".join(current_parts))
            in_si = False

    def char_data(data: str) -> None:
        if in_t:
            current_parts.append(data)

    parser = xml.parsers.expat.ParserCreate()
    parser.StartElementHandler = start_el
    parser.EndElementHandler = end_el
    parser.CharacterDataHandler = char_data
    parser.Parse(xml_bytes, True)
    return strings


def _first_sheet_info(z: zipfile.ZipFile) -> tuple[str, str]:
    """Return ``(first_sheet_name, worksheet_zip_member)`` from an open ``.xlsx``."""
    names = set(z.namelist())
    sheet_name = ""
    if "xl/workbook.xml" in names:
        wb_root = ET.fromstring(z.read("xl/workbook.xml"))
        for el in wb_root.iter():
            if el.tag.endswith("}sheet") or el.tag == "sheet":
                sheet_name = (el.attrib.get("name") or "").strip()
                break

    if "xl/worksheets/sheet1.xml" in names:
        return sheet_name, "xl/worksheets/sheet1.xml"

    candidates = sorted(
        n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    )
    if not candidates:
        raise ValueError("No worksheet XML found inside archive")
    return sheet_name, candidates[0]


def _col_letters(cell_ref: str) -> str:
    i = 0
    n = len(cell_ref)
    while i < n and cell_ref[i].isalpha():
        i += 1
    return cell_ref[:i]


def _parse_excel_date(raw_val: str) -> date | None:
    text = raw_val.strip()
    if not text or text.lower() in MISSING_TOKENS:
        return None
    # Fast path: Excel serial number (e.g. "46336" or "46336.0")
    ch0 = text[0]
    if ch0.isdigit() and "-" not in text and "/" not in text and "T" not in text:
        try:
            serial = int(float(text))
            if 1000 <= serial <= 100000:
                return (EXCEL_EPOCH + timedelta(days=serial)).date()
        except ValueError:
            pass

    # ISO YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass

    # DD/MM/YYYY
    if len(text) >= 10 and text[2] == "/" and text[5] == "/":
        try:
            return datetime.strptime(text[:10], "%d/%m/%Y").date()
        except ValueError:
            pass

    return None


def _parse_float(raw_val: str | None) -> float:
    if raw_val is None:
        return float("nan")
    text = raw_val.strip()
    if not text or text.lower() in MISSING_TOKENS:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return float("nan")


@dataclass(slots=True)
class XlsxAuditInfo:
    path: Path
    filename: str
    sheet_name: str
    ticker: str
    company_name: str
    source_vendor: str
    header_row: int | None
    columns_detected: tuple[str, ...]
    ebitda_window_months: int | None
    raw_ebitda_header: str
    is_copy_filename: bool
    error: str | None = None


def inspect_xlsx_header(path: Path | str, max_scan_rows: int = 12) -> XlsxAuditInfo:
    """Inspect metadata and header rows of an ``.xlsx`` file in <1ms without reading all rows."""
    file_path = Path(path)
    filename = file_path.name
    stem = file_path.stem.strip()
    is_copy = bool(COPY_FILENAME_RE.search(stem))

    try:
        with zipfile.ZipFile(file_path, "r") as z:
            sheet_name, sheet_member = _first_sheet_info(z)
            shared: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                shared = _parse_shared_strings(z.read("xl/sharedStrings.xml"))

            rows_scanned: dict[int, dict[str, str]] = {}
            current_row = 0
            current_col = ""
            current_type = ""
            in_val = False
            val_parts: list[str] = []

            class _StopScan(Exception):
                pass

            def start_el(name: str, attrs: dict[str, str]) -> None:
                nonlocal current_row, current_col, current_type, in_val
                local = name.rsplit(":", 1)[-1]
                if local == "row":
                    r_attr = attrs.get("r")
                    current_row = int(r_attr) if r_attr and r_attr.isdigit() else (current_row + 1)
                    if current_row > max_scan_rows:
                        raise _StopScan
                    rows_scanned[current_row] = {}
                elif local == "c" and 1 <= current_row <= max_scan_rows:
                    ref = attrs.get("r", "")
                    current_col = _col_letters(ref)
                    current_type = attrs.get("t", "")
                    val_parts.clear()
                elif local in {"v", "t"} and 1 <= current_row <= max_scan_rows and current_col:
                    in_val = True

            def end_el(name: str) -> None:
                nonlocal in_val, current_col
                local = name.rsplit(":", 1)[-1]
                if local in {"v", "t"}:
                    in_val = False
                elif local == "c" and 1 <= current_row <= max_scan_rows and current_col:
                    raw_text = "".join(val_parts)
                    if current_type == "s":
                        try:
                            idx = int(raw_text)
                            resolved = shared[idx] if 0 <= idx < len(shared) else raw_text
                        except ValueError:
                            resolved = raw_text
                    else:
                        resolved = raw_text
                    rows_scanned[current_row][current_col] = resolved
                    current_col = ""

            def char_data(data: str) -> None:
                if in_val:
                    val_parts.append(data)

            parser = xml.parsers.expat.ParserCreate()
            parser.StartElementHandler = start_el
            parser.EndElementHandler = end_el
            parser.CharacterDataHandler = char_data

            with z.open(sheet_member) as fp:
                try:
                    while chunk := fp.read(16384):
                        parser.Parse(chunk, False)
                    parser.Parse(b"", True)
                except _StopScan:
                    pass

            row1 = rows_scanned.get(1, {})
            company_name = ""
            source_vendor = ""
            header_row: int | None = None
            detected_cols: list[str] = []
            ebitda_window: int | None = None
            raw_ebitda_hdr = ""

            for r_idx in sorted(rows_scanned.keys()):
                row_cells = rows_scanned[r_idx]
                mapped: list[str] = []
                row_ebitda_win: int | None = None
                row_ebitda_hdr = ""
                for _, cell_val in sorted(row_cells.items()):
                    canon, meta = classify_column_header(cell_val)
                    if canon:
                        mapped.append(canon)
                        if canon == "EBITDA":
                            row_ebitda_win = meta.get("ebitda_window_months")
                            row_ebitda_hdr = meta.get("raw_ebitda_header", "")
                if "Date" in mapped and ("EBITDA" in mapped or "EV" in mapped or "Price" in mapped):
                    header_row = r_idx
                    detected_cols = mapped
                    ebitda_window = row_ebitda_win
                    raw_ebitda_hdr = row_ebitda_hdr
                    break

            if header_row is not None and header_row > 1:
                company_name = (row1.get("A") or "").strip()
                source_vendor = (row1.get("E") or "").strip()

            ticker = normalize_ticker_name(sheet_name, stem)
            return XlsxAuditInfo(
                path=file_path,
                filename=filename,
                sheet_name=sheet_name,
                ticker=ticker,
                company_name=company_name or ticker,
                source_vendor=source_vendor,
                header_row=header_row,
                columns_detected=tuple(detected_cols),
                ebitda_window_months=ebitda_window,
                raw_ebitda_header=raw_ebitda_hdr,
                is_copy_filename=is_copy,
            )
    except Exception as exc:  # noqa: BLE001
        return XlsxAuditInfo(
            path=file_path,
            filename=filename,
            sheet_name="",
            ticker=stem,
            company_name=stem,
            source_vendor="",
            header_row=None,
            columns_detected=(),
            ebitda_window_months=None,
            raw_ebitda_header="",
            is_copy_filename=is_copy,
            error=str(exc),
        )


GENERIC_SHEET_NAMES = {"sheet1", "sheet", "plan1", "planilha1", "dados", "data"}


def normalize_ticker_name(sheet_name: str, file_stem: str) -> str:
    """Resolve canonical ticker from Economatica ``sheet_name`` or fallback to ``file_stem``."""
    clean_sheet = (sheet_name or "").strip()
    if clean_sheet and clean_sheet.lower() not in GENERIC_SHEET_NAMES:
        return clean_sheet.upper()
    # Clean copy suffix if present in file_stem
    cleaned_stem = COPY_FILENAME_RE.sub("", file_stem).strip()
    return (cleaned_stem or file_stem).upper()


def extract_issuer_code(ticker: str) -> str:
    """Extract 4-character B3 issuer root (e.g. ``PETR4`` -> ``PETR``, ``SANB11`` -> ``SANB``).

    For numeric CVM codes like ``024465 ON``, returns ``024465``.
    """
    t = ticker.strip().upper()
    m_b3 = re.match(r"^([A-Z0-9]{4})\d{1,2}[A-Z]?$", t)
    if m_b3:
        return m_b3.group(1)
    if "-" in t:
        return t.split("-", 1)[0].strip()
    if " " in t:
        return t.split()[0].strip()
    return t


@dataclass(slots=True)
class ParsedAssetSheet:
    ticker: str
    company_name: str
    filename: str
    ebitda_window_months: int | None
    dates: list[date]
    prices: list[float]
    ebitdas: list[float]
    evs: list[float]
    roics: list[float]


def parse_xlsx_timeseries(path: Path | str) -> ParsedAssetSheet | None:
    """Parse full time series from an Economatica or standard ``.xlsx`` file using C expat."""
    file_path = Path(path)
    with zipfile.ZipFile(file_path, "r") as z:
        sheet_name, sheet_member = _first_sheet_info(z)
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            shared = _parse_shared_strings(z.read("xl/sharedStrings.xml"))
        xml_bytes = z.read(sheet_member)

    header_row: int | None = None
    col_map: dict[str, str] = {}  # e.g. {'A': 'Date', 'B': 'Price', ...}
    ebitda_window: int | None = None
    company_name = ""

    dates: list[date] = []
    prices: list[float] = []
    ebitdas: list[float] = []
    evs: list[float] = []
    roics: list[float] = []

    current_row = 0
    current_col = ""
    current_type = ""
    in_val = False
    val_parts: list[str] = []
    row_cells: dict[str, str] = {}

    nan = float("nan")
    col_date = ""
    col_price = ""
    col_ebitda = ""
    col_ev = ""
    col_roic = ""

    def start_el(name: str, attrs: dict[str, str]) -> None:
        nonlocal current_row, current_col, current_type, in_val
        local = name.rsplit(":", 1)[-1]
        if local == "row":
            r_attr = attrs.get("r")
            current_row = int(r_attr) if r_attr and r_attr.isdigit() else (current_row + 1)
            row_cells.clear()
        elif local == "c":
            ref = attrs.get("r", "")
            current_col = _col_letters(ref)
            current_type = attrs.get("t", "")
            val_parts.clear()
        elif local in {"v", "t"} and current_col:
            in_val = True

    def end_el(name: str) -> None:
        nonlocal in_val, current_col, header_row, ebitda_window, company_name
        nonlocal col_date, col_price, col_ebitda, col_ev, col_roic
        local = name.rsplit(":", 1)[-1]
        if local in {"v", "t"}:
            in_val = False
        elif local == "c" and current_col:
            raw_text = "".join(val_parts)
            if current_type == "s":
                try:
                    idx = int(raw_text)
                    resolved = shared[idx] if 0 <= idx < len(shared) else raw_text
                except ValueError:
                    resolved = raw_text
            elif current_type == "e":
                resolved = ""
            else:
                resolved = raw_text
            row_cells[current_col] = resolved
            current_col = ""
        elif local == "row":
            if header_row is None:
                if current_row == 1:
                    company_name = (row_cells.get("A") or "").strip()
                if current_row <= 12 and row_cells:
                    temp_map: dict[str, str] = {}
                    temp_win: int | None = None
                    for c_key, c_val in row_cells.items():
                        canon, meta = classify_column_header(c_val)
                        if canon and canon not in temp_map.values():
                            temp_map[canon] = c_key
                            if canon == "EBITDA":
                                temp_win = meta.get("ebitda_window_months")
                    if "Date" in temp_map and ("EBITDA" in temp_map or "EV" in temp_map or "Price" in temp_map):
                        header_row = current_row
                        col_map.update(temp_map)
                        ebitda_window = temp_win
                        col_date = temp_map.get("Date", "")
                        col_price = temp_map.get("Price", "")
                        col_ebitda = temp_map.get("EBITDA", "")
                        col_ev = temp_map.get("EV", "")
                        col_roic = temp_map.get("ROIC", "")
                        if current_row == 1:
                            company_name = ""
            else:
                raw_d = row_cells.get(col_date, "")
                if not raw_d:
                    return
                dt = _parse_excel_date(raw_d)
                if dt is None:
                    return
                dates.append(dt)
                prices.append(_parse_float(row_cells.get(col_price)) if col_price else nan)
                ebitdas.append(_parse_float(row_cells.get(col_ebitda)) if col_ebitda else nan)
                evs.append(_parse_float(row_cells.get(col_ev)) if col_ev else nan)
                roics.append(_parse_float(row_cells.get(col_roic)) if col_roic else nan)

    def char_data(data: str) -> None:
        if in_val:
            val_parts.append(data)

    parser = xml.parsers.expat.ParserCreate()
    parser.StartElementHandler = start_el
    parser.EndElementHandler = end_el
    parser.CharacterDataHandler = char_data
    parser.Parse(xml_bytes, True)

    if header_row is None or not dates:
        return None

    ticker = normalize_ticker_name(sheet_name, file_path.stem)
    return ParsedAssetSheet(
        ticker=ticker,
        company_name=company_name or ticker,
        filename=file_path.name,
        ebitda_window_months=ebitda_window,
        dates=dates,
        prices=prices,
        ebitdas=ebitdas,
        evs=evs,
        roics=roics,
    )
