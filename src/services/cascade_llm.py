"""LLM-адаптер для второго этапа каскадирования (feature-flag)."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

from src.core.config import settings
from src.services.llm import chat_completion


def norm_text(value: object) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def pair_hash(employee_kpi: str, board_kpi: str, judge_model: str) -> str:
    payload = "||".join([norm_text(employee_kpi), norm_text(board_kpi), norm_text(judge_model)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CascadeLlmAdapter:
    """Изолированный адаптер: подключается только если включен флаг."""

    def __init__(self) -> None:
        self.enabled = bool(getattr(settings, "enable_cascade_llm", False))

    def is_enabled(self) -> bool:
        return self.enabled

    def judge_pair(self, employee_kpi: str, manager_kpi: str) -> Optional[dict[str, object]]:
        if not self.enabled:
            return None
        model = getattr(settings, "cascade_llm_judge_model", "qwen3:8b")
        prompt = (
            "Ты эксперт по каскадированию KPI.\n"
            "Оцени соответствие KPI заместителя цели руководителя.\n"
            "Верни JSON: decision(match|partial|no_match), confidence(0..1), reason.\n\n"
            f"KPI заместителя: {employee_kpi}\n"
            f"KPI руководителя: {manager_kpi}\n"
        )
        raw = chat_completion(
            [{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
            use_ollama=True,
            timeout=getattr(settings, "cascade_llm_timeout_sec", 120.0),
        )
        if not raw:
            return None
        return {"raw": raw}
