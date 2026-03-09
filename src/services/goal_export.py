"""
Извлечение таблицы целей (РАЗДЕЛ 8) из текста ответа LLM и генерация xlsx.

Промпт (data/prompt.txt) требует вывести таблицу в формате CSV с разделителем «;».
Этот модуль находит блок таблицы в тексте, парсит CSV и формирует файл Excel.
"""

import io
import re
from typing import Dict, List, Optional

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

def _norm(s: str) -> str:
    return str(s).lower().strip().replace(" ", "").replace("ё", "е").replace("-", "")


# Маппинг возможных заголовков CSV от LLM (нормализованные) на индекс в EXCEL_HEADERS
def _build_header_aliases() -> Dict[str, int]:
    aliases: Dict[str, int] = {}
    for i, h in enumerate(EXCEL_HEADERS):
        aliases[_norm(h)] = i
    aliases[_norm("Единица измерения")] = 5
    aliases[_norm("Методика расчета")] = 17
    return aliases


HEADER_ALIASES = _build_header_aliases()


def _find_goals_table_block(content: str) -> Optional[str]:
    """Найти в тексте блок с таблицей целей (РАЗДЕЛ 8 / ТАБЛИЦА ЦЕЛЕЙ)."""
    if not content or not content.strip():
        return None
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    # Ищем начало: РАЗДЕЛ 8 или ТАБЛИЦА ЦЕЛЕЙ (ФОРМА) или аналоги
    start_markers = [
        "РАЗДЕЛ 8",
        "ТАБЛИЦА ЦЕЛЕЙ",
        "таблица целей",
        "РАЗДЕЛ 8.",
        "———\nРАЗДЕЛ 8",
    ]
    start_pos = -1
    for marker in start_markers:
        idx = content.find(marker)
        if idx != -1:
            start_pos = idx
            break
    if start_pos == -1:
        # Попробуем взять любой блок строк, содержащих «;» (CSV-подобный)
        for line in content.split("\n"):
            if ";" in line and (_norm("цел") in _norm(line) or _norm("кпэ") in _norm(line)):
                start_pos = content.find(line)
                break
        if start_pos == -1:
            return None
    # Конец блока: следующий РАЗДЕЛ или пустая строка подряд или конец
    rest = content[start_pos:]
    end_pos = len(rest)
    for m in re.finditer(r"\n\s*РАЗДЕЛ\s+\d", rest):
        end_pos = m.start()
        break
    if end_pos == len(rest):
        # Обрезать по двум подряд пустым строкам
        parts = rest.split("\n\n\n")
        if parts:
            rest = parts[0]
        end_pos = len(rest)
    block = rest[:end_pos].strip()
    if ";" not in block:
        return None
    # Оставить только строки, похожие на CSV (с разделителем ;)
    lines = [ln for ln in block.split("\n") if ";" in ln]
    return "\n".join(lines) if lines else None


def _parse_csv_block(block: str) -> List[List[str]]:
    """Парсинг CSV с разделителем «;». Кавычки учитываем (упрощённо)."""
    rows: List[List[str]] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Простой split по ; (если внутри кавычек — не разбивать; для LLM обычно без кавычек)
        cells: List[str] = []
        current = ""
        in_quotes = False
        for i, c in enumerate(line):
            if c == '"':
                in_quotes = not in_quotes
                current += c
            elif c == ";" and not in_quotes:
                cells.append(current.strip().strip('"'))
                current = ""
            else:
                current += c
        cells.append(str(current.strip().strip('"') or ""))
        rows.append(cells)
    return rows


def _map_row_to_excel_row(cells: List[str], header_indices: Optional[List[int]]) -> List[str]:
    """Преобразовать строку CSV в строку для Excel (20 колонок как EXCEL_HEADERS)."""
    out: List[str] = [""] * len(EXCEL_HEADERS)
    if header_indices is not None:
        for col_idx, excel_idx in enumerate(header_indices):
            if 0 <= excel_idx < len(out) and col_idx < len(cells):
                out[excel_idx] = str(cells[col_idx]).strip() if col_idx < len(cells) else ""
    else:
        # По позиции: совпадение с типовым шаблоном (№ цели, Наименование, Тип, Вид, Ед.изм., Q1 вес, Q1 план, ...)
        for i, val in enumerate(cells):
            if i < len(out):
                out[i] = str(val).strip()
    return out


def _infer_header_mapping(first_row: List[str]) -> Optional[List[int]]:
    """По первой строке CSV определить маппинг колонок на EXCEL_HEADERS."""
    mapping: List[int] = []
    for cell in first_row:
        key = _norm(str(cell))
        idx = HEADER_ALIASES.get(key)
        if idx is not None:
            mapping.append(idx)
        else:
            # Попытка по частичному совпадению (например «I кв. Вес %»)
            found = -1
            for i, h in enumerate(EXCEL_HEADERS):
                if key in _norm(h) or _norm(h) in key:
                    found = i
                    break
            mapping.append(found if found >= 0 else -1)
    return mapping if any(x >= 0 for x in mapping) else None


def extract_goals_table_from_content(content: str) -> List[List[str]]:
    """
    Извлечь из текста ответа LLM таблицу целей и вернуть строки для Excel
    (каждая строка — список значений по колонкам EXCEL_HEADERS).
    """
    block = _find_goals_table_block(content)
    if not block:
        return []
    rows = _parse_csv_block(block)
    if not rows:
        return []
    # Первая строка — заголовок?
    header_indices: Optional[List[int]] = None
    data_start = 0
    if rows and any(_norm(str(c)).replace("%", "").replace(".", "") in ("цели", "кпэ", "наименование", "тип", "вид", "вес", "план", "квартал") for c in rows[0]):
        header_indices = _infer_header_mapping(rows[0])
        data_start = 1
    result: List[List[str]] = []
    for row in rows[data_start:]:
        if not any(c.strip() for c in row):
            continue
        result.append(_map_row_to_excel_row(row, header_indices))
    return result


def build_goals_xlsx(rows: List[List[str]]) -> bytes:
    """Собрать xlsx с листом «Цели» и вернуть байты файла."""
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
    """
    По тексту ответа LLM извлечь таблицу целей и вернуть xlsx.
    Если таблица не найдена, возвращает None.
    """
    if content is None:
        content = ""
    content = str(content)
    # Ограничиваем размер, чтобы не перегружать память (примерно 2 МБ текста)
    if len(content) > 2_000_000:
        content = content[:2_000_000]
    rows = extract_goals_table_from_content(content)
    if not rows:
        return None
    return build_goals_xlsx(rows)
