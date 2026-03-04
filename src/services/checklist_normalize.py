"""
Нормализация чеклистов (items/sections/rules) для сохранения в JSON.
Используется и для шаблонных документов, и для пользовательских файлов.
"""
from typing import Any


def normalize_checklist_items(raw_items: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(raw_items, list):
        return items
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        items.append(
            {
                "id": str(raw.get("id") or "").strip(),
                "text": str(raw.get("text") or "").strip(),
                "section": str(raw.get("section") or "").strip(),
                "checked": bool(raw.get("checked")) if raw.get("checked") is not None else False,
            }
        )
    return items


def normalize_checklist_sections(raw_sections: Any, items: list[dict[str, Any]]) -> list[str]:
    if isinstance(raw_sections, list):
        cleaned = [str(s).strip() for s in raw_sections if str(s).strip()]
        if cleaned:
            return cleaned
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        section = str(item.get("section") or "").strip()
        if section and section not in seen:
            seen.add(section)
            ordered.append(section)
    return ordered


def normalize_checklist_json(doc_type: str, raw_json: dict[str, Any]) -> dict[str, Any]:
    if doc_type in ("strategy_checklist", "business_plan_checklist"):
        items = normalize_checklist_items(raw_json.get("items"))
        sections = normalize_checklist_sections(raw_json.get("sections"), items)
        return {"sections": sections, "items": items}
    if doc_type == "reglament_checklist":
        rules_raw = raw_json.get("rules")
        if not rules_raw and isinstance(raw_json.get("items"), list):
            rules_raw = raw_json.get("items")
        rules = normalize_checklist_items(rules_raw)
        return {"rules": rules}
    return raw_json
