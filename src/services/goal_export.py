"""
Извлечение таблицы целей (РАЗДЕЛ 8) из текста ответа LLM и генерация xlsx.

Промпт просит CSV с разделителем «;», но модели часто выводят Markdown-таблицы (|...|),
TAB или запятые. Этот модуль ищет блок раздела 8 и пробует несколько форматов.
"""

import csv
import io
import re
from typing import Callable, Dict, List, Optional, Tuple

import openpyxl

# Заголовки листа «Цели» в xlsx (как в frontend exportLeaderGoalsExcel)
EXCEL_HEADERS = [
    "ФИО",
    "№ цели",
    "Наименование КПЭ",
    "Тип цели",
    "Вид цели",
    "Ед. изм.",
    "I кв. Вес %",
    "I кв. План. / веха",
    "II кв. Вес %",
    "II кв. План. / веха",
    "III кв. Вес %",
    "III кв. План. / веха",
    "IV кв. Вес %",
    "IV кв. План. / веха",
    "Год Вес %",
    "Год План. / веха",
    "Комментарии",
    "Методика расчёта",
    "Источник информации",
    "Отчётный год",
]

# Минимум колонок, чтобы считать строку строкой таблицы целей (не случайный текст)
_MIN_TABLE_COLS = 4


def _norm(s: str) -> str:
    return str(s).lower().strip().replace(" ", "").replace("ё", "е").replace("-", "")


def _build_header_aliases() -> Dict[str, int]:
    aliases: Dict[str, int] = {}
    for i, h in enumerate(EXCEL_HEADERS):
        aliases[_norm(h)] = i
    aliases[_norm("Единица измерения")] = 5
    aliases[_norm("Методика расчета")] = 17
    aliases[_norm("План./веха")] = 7
    aliases[_norm("Плановое значение")] = 7
    return aliases


HEADER_ALIASES = _build_header_aliases()

_SECTION_START_RE = re.compile(
    r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:РАЗДЕЛ|Раздел)\s*[:\.\-—]?\s*8\b",
    re.IGNORECASE | re.MULTILINE,
)


def _locate_raw_section_block(content: str) -> Optional[str]:
    """Вырезать текст от «Раздел 8» / «РАЗДЕЛ 8» до следующего раздела или конца осмысленного блока."""
    if not content or not content.strip():
        return None
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    start_pos = -1

    m = _SECTION_START_RE.search(text)
    if m:
        start_pos = m.start()
    if start_pos < 0:
        for marker in (
            "ТАБЛИЦА ЦЕЛЕЙ",
            "Таблица целей",
            "таблица целей (форма)",
        ):
            idx = text.find(marker)
            if idx != -1:
                start_pos = idx
                break

    if start_pos < 0:
        # Фолбэк: первая строка с «;» и признаками целей/КПЭ
        for line in text.split("\n"):
            if ";" in line and ("кпэ" in line.lower() or "цел" in line.lower() or "фио" in line.lower()):
                start_pos = text.find(line)
                break

    if start_pos < 0:
        return None

    rest = text[start_pos:]
    end_pos = len(rest)
    for sep in re.finditer(r"\n\s*(?:#{0,4}\s*)?(?:РАЗДЕЛ|Раздел)\s*[:\.\-—]?\s*(?!8\b)\d+", rest, re.IGNORECASE):
        end_pos = sep.start()
        break
    if end_pos == len(rest):
        parts = rest.split("\n\n\n")
        rest = parts[0] if parts else rest
        end_pos = len(rest)

    return rest[:end_pos].strip() or None


def _parse_semicolon_block(block: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line or ";" not in line:
            continue
        cells: List[str] = []
        current = ""
        in_quotes = False
        for c in line:
            if c == '"':
                in_quotes = not in_quotes
                current += c
            elif c == ";" and not in_quotes:
                cells.append(current.strip().strip('"'))
                current = ""
            else:
                current += c
        cells.append(str(current.strip().strip('"') or ""))
        if len(cells) >= _MIN_TABLE_COLS:
            rows.append(cells)
    return rows


def _is_markdown_separator_line(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    inner = s.strip("|").strip()
    return bool(re.match(r"^[\s|\-:_]+$", inner))


def _parse_markdown_table(block: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in block.split("\n"):
        line = line.rstrip()
        if "|" not in line:
            continue
        if not line.strip().startswith("|"):
            line = "|" + line.strip()
        if not line.rstrip().endswith("|"):
            line = line.rstrip() + "|"
        if _is_markdown_separator_line(line):
            continue
        cells = [re.sub(r"\*+", "", c).strip() for c in line.strip("|").split("|")]
        if len(cells) >= _MIN_TABLE_COLS:
            rows.append(cells)
    return rows


def _parse_tab_block(block: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in block.split("\n"):
        if "\t" not in line:
            continue
        cells = [c.strip() for c in line.split("\t")]
        if len(cells) >= _MIN_TABLE_COLS:
            rows.append(cells)
    return rows


def _parse_comma_block(block: str) -> List[List[str]]:
    rows: List[List[str]] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line or line.count(",") < 3:
            continue
        try:
            cells = next(csv.reader([line], delimiter=","))
        except Exception:
            continue
        cells = [c.strip() for c in cells]
        if len(cells) >= _MIN_TABLE_COLS:
            rows.append(cells)
    return rows


def _parse_rows_from_block(block: str) -> List[List[str]]:
    """Пробуем форматы в порядке от наиболее специфичного к общему."""
    if not block:
        return []
    parsers: Tuple[Callable[[str], List[List[str]]], ...] = (
        _parse_semicolon_block,
        _parse_markdown_table,
        _parse_tab_block,
        _parse_comma_block,
    )
    for parse_fn in parsers:
        rows = parse_fn(block)
        if len(rows) >= 1:
            return rows
    return []


def _fulltext_markdown_fallback(content: str) -> List[List[str]]:
    """Если маркер раздела не найден, но в конце ответа есть markdown-таблица с КПЭ/целями."""
    rows = _parse_markdown_table(content)
    if len(rows) < 1:
        return []
    joined = " ".join(_norm(" ".join(r)) for r in rows[:3])
    if "кпэ" in joined or "цел" in joined or "фио" in joined or "вес" in joined:
        return rows
    return []

def _extract_after_colon(line: str) -> str:
    m = re.search(r"[:\-]\s*(.+)$", line.strip())
    if m:
        return m.group(1).strip()
    return ""

def _split_semistructured_blocks(text: str) -> List[List[str]]:
    """
    Грубый фолбэк: разбить текст на блоки KPI по нумерации/маркерам.
    Пример:
    1) KPI ...
    Тип: ...
    Ед. изм.: ...
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    blocks: List[List[str]] = []
    current: List[str] = []
    block_start = re.compile(r"^(?:\d{1,2}[).]|[-*•]\s+|kpi\s*\d+)", re.IGNORECASE)
    for ln in lines:
        if block_start.match(ln) and current:
            blocks.append(current)
            current = [ln]
        else:
            current.append(ln)
    if current:
        blocks.append(current)
    return blocks

def _parse_semistructured_goal_blocks(content: str) -> List[List[str]]:
    """
    Фолбэк для ответов без таблицы: достаём ключевые поля из абзацев/списков.
    Заполняются только найденные колонки, остальные остаются пустыми.
    """
    section = _locate_raw_section_block(content) or content
    blocks = _split_semistructured_blocks(section)
    out_rows: List[List[str]] = []
    for block in blocks:
        row = [""] * len(EXCEL_HEADERS)
        for ln in block:
            lower = ln.lower()
            if ("фио" in lower or "владел" in lower) and not row[0]:
                row[0] = _extract_after_colon(ln)
            elif ("№ цели" in lower or lower.startswith("№")) and not row[1]:
                row[1] = _extract_after_colon(ln)
            elif ("кпэ" in lower or "kpi" in lower or "наименование" in lower or "цель" in lower) and not row[2]:
                row[2] = _extract_after_colon(ln) or re.sub(r"^\d{1,2}[).]\s*", "", ln).strip()
            elif "тип" in lower and not row[3]:
                row[3] = _extract_after_colon(ln)
            elif "вид" in lower and not row[4]:
                row[4] = _extract_after_colon(ln)
            elif ("ед." in lower or "измер" in lower) and not row[5]:
                row[5] = _extract_after_colon(ln)
            elif ("q1" in lower or "i кв" in lower) and not row[7]:
                row[7] = _extract_after_colon(ln)
            elif ("q2" in lower or "ii кв" in lower) and not row[9]:
                row[9] = _extract_after_colon(ln)
            elif ("q3" in lower or "iii кв" in lower) and not row[11]:
                row[11] = _extract_after_colon(ln)
            elif ("q4" in lower or "iv кв" in lower) and not row[13]:
                row[13] = _extract_after_colon(ln)
            elif ("год" in lower and "план" in lower) and not row[15]:
                row[15] = _extract_after_colon(ln)
            elif ("методик" in lower) and not row[17]:
                row[17] = _extract_after_colon(ln)
            elif ("источник" in lower) and not row[18]:
                row[18] = _extract_after_colon(ln)
            elif ("отчет" in lower or "отчёт" in lower) and not row[19]:
                row[19] = _extract_after_colon(ln)
        # Минимум: название KPI/цели должно быть
        if row[2]:
            out_rows.append(row)
    return out_rows


def _first_row_looks_like_header(row: List[str]) -> bool:
    if not row:
        return False
    tokens = ("цел", "кпэ", "наименование", "тип", "вид", "вес", "план", "квартал", "фио", "ед", "изм", "методика", "источник", "отчет")
    for c in row:
        n = _norm(str(c)).replace("%", "").replace(".", "")
        for t in tokens:
            if t in n:
                return True
    return False


def _map_row_to_excel_row(cells: List[str], header_indices: Optional[List[int]]) -> List[str]:
    out: List[str] = [""] * len(EXCEL_HEADERS)
    if header_indices is not None:
        for col_idx, excel_idx in enumerate(header_indices):
            if 0 <= excel_idx < len(out) and col_idx < len(cells):
                out[excel_idx] = str(cells[col_idx]).strip() if col_idx < len(cells) else ""
    else:
        for i, val in enumerate(cells):
            if i < len(out):
                out[i] = str(val).strip()
    return out


def _infer_header_mapping(first_row: List[str]) -> Optional[List[int]]:
    mapping: List[int] = []
    for cell in first_row:
        key = _norm(str(cell))
        idx = HEADER_ALIASES.get(key)
        if idx is not None:
            mapping.append(idx)
        else:
            found = -1
            for i, h in enumerate(EXCEL_HEADERS):
                if key and (key in _norm(h) or _norm(h) in key):
                    found = i
                    break
            mapping.append(found if found >= 0 else -1)
    return mapping if any(x >= 0 for x in mapping) else None


def extract_goals_table_from_content(content: str) -> List[List[str]]:
    """
    Извлечь из текста ответа LLM таблицу целей и вернуть строки для Excel
    (каждая строка — список значений по колонкам EXCEL_HEADERS).
    """
    block = _locate_raw_section_block(content)
    rows: List[List[str]] = []
    if block:
        rows = _parse_rows_from_block(block)
    if not rows:
        rows = _fulltext_markdown_fallback(content)
    if not rows:
        # последний шанс: семиколон по всему тексту
        rows = _parse_semicolon_block(content.replace("\r\n", "\n").replace("\r", "\n"))
    if not rows:
        # авто-ремонт: пробуем собрать строки из полуструктурированного текста
        rows = _parse_semistructured_goal_blocks(content)
    if not rows:
        return []

    header_indices: Optional[List[int]] = None
    data_start = 0
    if rows and _first_row_looks_like_header(rows[0]):
        header_indices = _infer_header_mapping(rows[0])
        if header_indices is not None:
            data_start = 1

    result: List[List[str]] = []
    for row in rows[data_start:]:
        if not any(str(c).strip() for c in row):
            continue
        result.append(_map_row_to_excel_row(row, header_indices))
    return result


def build_goals_xlsx(rows: List[List[str]]) -> bytes:
    wb = openpyxl.Workbook(write_only=False)
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Цели", 0)
    else:
        ws.title = "Цели"
    ws.append(EXCEL_HEADERS)
    for row in rows:
        if not isinstance(row, (list, tuple)):
            row = []
        ws.append([str(c) for c in row])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_goals_xlsx_from_llm_response(content: str) -> Optional[bytes]:
    if content is None:
        content = ""
    content = str(content)
    if len(content) > 2_000_000:
        content = content[:2_000_000]
    rows = extract_goals_table_from_content(content)
    if not rows:
        return None
    return build_goals_xlsx(rows)
