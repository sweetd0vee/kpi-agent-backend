"""LLM-адаптер для второго этапа каскадирования (feature-flag)."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from typing import Optional

from src.core.config import settings
from src.services.llm import chat_completion

logger = logging.getLogger(__name__)


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

    def judge_pair(
        self,
        employee_kpi: str,
        manager_kpi: str,
        *,
        force: bool = False,
    ) -> Optional[dict[str, object]]:
        if not self.enabled and not force:
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

    def assess_goal_relevance(
        self,
        *,
        subject_name: str,
        process_names: list[str],
        goal_title: str,
        goal_metric: str,
        force: bool = False,
    ) -> Optional[dict[str, object]]:
        if not self.enabled and not force:
            return None
        if not process_names:
            return None
        started_at = time.perf_counter()
        model = getattr(settings, "cascade_llm_judge_model", "qwen3:8b")
        process_text = "\n".join(f"- {name}" for name in process_names[:50])
        prompt = (
            "Ты эксперт по каскадированию KPI и процессному управлению.\n"
            "Оцени, релевантна ли цель руководителя процессам сотрудника из реестра процессов.\n"
            "Верни строго JSON без пояснений:\n"
            '{"relevant": true|false, "confidence": 0..1, "reason": "кратко"}\n\n'
            f"Сотрудник (получатель цели): {subject_name}\n"
            f"Процессы сотрудника:\n{process_text}\n\n"
            f"Цель руководителя: {goal_title}\n"
            f"Метрика цели: {goal_metric}\n"
        )
        raw = chat_completion(
            [{"role": "user", "content": prompt}],
            model=model,
            temperature=0.1,
            use_ollama=True,
            timeout=getattr(settings, "cascade_llm_timeout_sec", 120.0),
        )
        if not raw:
            logger.warning(
                "LLM relevance '%s': empty response (model=%s, processes=%s, elapsed=%.2fs)",
                subject_name,
                model,
                len(process_names),
                time.perf_counter() - started_at,
            )
            return None
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            logger.warning(
                "LLM relevance '%s': invalid JSON response (model=%s, elapsed=%.2fs)",
                subject_name,
                model,
                time.perf_counter() - started_at,
            )
            return None
        relevant = bool(parsed.get("relevant"))
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = str(parsed.get("reason") or "").strip()
        logger.info(
            "LLM relevance '%s': relevant=%s confidence=%.3f model=%s elapsed=%.2fs",
            subject_name,
            relevant,
            confidence,
            model,
            time.perf_counter() - started_at,
        )
        return {"relevant": relevant, "confidence": confidence, "reason": reason}


def _extract_json(raw: str) -> Optional[dict]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text, flags=re.IGNORECASE)
    if "{" not in text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    chunk = text[start : end + 1]
    try:
        parsed = json.loads(chunk)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None
