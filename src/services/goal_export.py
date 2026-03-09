"""
Извлечение таблицы целей (РАЗДЕЛ 8) из текста ответа LLM и генерация xlsx.

Промпт (data/prompt.txt) требует вывести таблицу в формате CSV с разделителем «;».
Этот модуль находит блок таблицы в тексте, парсит CSV и формирует файл Excel.
"""

import io
import re
import uuid
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

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

# Маппинг возможных заголовков CSV от LLM (нормализованные) на индекс в EXCEL_HEADERS (1-based: ФИО=0, № цели=1, ...)
HEADER_ALIASES: dict[str, int] = {}
for i, h in enumerate(EXCEL_HEADERS):
    key = _norm(h)
    HEADER_ALIASES[key] = i
HEADER_ALIASES[_norm("№ цели")] = 1
HEADER_ALIASES[_norm("Наименование КПЭ")] = 2
HEADER_ALIASES[_norm("Тип цели")] = 3
HEADER_ALIASES[_norm("Вид цели")] = 4
HEADER_ALIASES[_norm("Единица измерения")] = 5
HEADER_ALIASES[_norm("Ед. изм.")] = 5
HEADER_ALIASES[_norm("Комментарии")] = 16
HEADER_ALIASES[_norm("Методика расчета")] = 17
HEADER_ALIASES[_norm("Методика расчёта")] = 17
HEADER_ALIASES[_norm("Источник информации")] = 18


def _norm(s: str) -> str:
    return s.lower().strip().replace(" ", "").replace("ё", "е").replace("-", "")


def _find_goals_table_block(content: str) -> str | None:
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
    return block if ";" in block else None


def _parse_csv_block(block: str) -> list[list[str]]:
    """Парсинг CSV с разделителем «;». Кавычки учитываем (упрощённо)."""
    rows: list[list[str]] = []
    for line in block.split("\n"):
        line = line.strip()
        if not line:
            continue
        # Простой split по ; (если внутри кавычек — не разбивать; для LLM обычно без кавычек)
        cells: list[str] = []
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
        cells.append(current.strip().strip('"'))
        rows.append(cells)
    return rows


def _map_row_to_excel_row(cells: list[str], header_indices: list[int] | None) -> list[str]:
    """Преобразовать строку CSV в строку для Excel (20 колонок как EXCEL_HEADERS)."""
    out: list[str] = [""] * len(EXCEL_HEADERS)
    if header_indices is not None:
        for col_idx, excel_idx in enumerate(header_indices):
            if 0 <= excel_idx < len(out) and col_idx < len(cells):
                out[excel_idx] = cells[col_idx].strip() if col_idx < len(cells) else ""
    else:
        # По позиции: совпадение с типовым шаблоном (№ цели, Наименование, Тип, Вид, Ед.изм., Q1 вес, Q1 план, ...)
        for i, val in enumerate(cells):
            if i < len(out):
                out[i] = val.strip()
    return out


def _infer_header_mapping(first_row: list[str]) -> list[int] | None:
    """По первой строке CSV определить маппинг колонок на EXCEL_HEADERS."""
    mapping: list[int] = []
    for cell in first_row:
        key = _norm(cell)
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
    if all(x >= 0 for x in mapping):
        return mapping
    return None


def extract_goals_table_from_content(content: str) -> list[list[str]]:
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
    header_indices: list[int] | None = None
    data_start = 0
    if rows and any(_norm(c).replace("%", "").replace(".", "") in ("цели", "кпэ", "наименование", "тип", "вид", "вес", "план", "квартал") for c in rows[0]):
        header_indices = _infer_header_mapping(rows[0])
        data_start = 1
    result: list[list[str]] = []
    for row in rows[data_start:]:
        if not any(c.strip() for c in row):
            continue
        result.append(_map_row_to_excel_row(row, header_indices))
    return result


def build_goals_xlsx(rows: list[list[str]]) -> bytes:
    """Собрать xlsx с листом «Цели» и вернуть байты файла."""
    wb = openpyxl.Workbook(write_only=False)
    ws = wb.active
    if ws is None:
        ws = wb.create_sheet("Цели", 0)
    else:
        ws.title = "Цели"
    ws.append(EXCEL_HEADERS)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_goals_xlsx_from_llm_response(content: str) -> bytes | None:
    """
    По тексту ответа LLM извлечь таблицу целей и вернуть xlsx.
    Если таблица не найдена, возвращает None.
    """
    rows = extract_goals_table_from_content(content)
    if not rows:
        return None
    return build_goals_xlsx(rows)
