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
            "Критерии строгости:\n"
            "1) relevant=true только если есть четкое содержательное совпадение цели с процессом,\n"
            "   либо частичное совпадение текста не менее 50%.\n"
            "2) Одного общего слова недостаточно (например: 'цифровой', 'разработка', 'система', 'проект').\n"
            "3) Если совпадение менее 50% или только по общим словам -> relevant=false.\n"
            "Верни строго JSON без пояснений:\n"
            '{"relevant": true|false, "confidence": 0..1, "overlap": 0..1, "matchType":"exact|partial|none", '
            '"matchedProcess":"", "reason":"кратко"}\n\n'
            f"Сотрудник (получатель цели): {subject_name}\n"
            f"Процессы сотрудника:\n{process_text}\n\n"
            f"Цель руководителя: {goal_title}\n"
            f"Метрика цели: {goal_metric}\n"
        )
        parsed = self._ask_json_with_fallback(prompt, model=model)
        if not parsed:
            logger.warning(
                "LLM relevance '%s': empty response (model=%s, processes=%s, elapsed=%.2fs)",
                subject_name,
                model,
                len(process_names),
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

    def assess_responsible_executor_match(
        self,
        *,
        deputy_name: str,
        responsible_executor: str,
        goal_title: str,
        initiative: str,
        force: bool = False,
    ) -> Optional[dict[str, object]]:
        """Сопоставляет ФИО заместителя со строкой "Ответственный исполнитель" из стратегии."""
        if not self.enabled and not force:
            return None
        if not deputy_name or not responsible_executor:
            return None
        started_at = time.perf_counter()
        model = getattr(settings, "cascade_llm_judge_model", "qwen3:8b")
        prompt = (
            "Ты эксперт по оргструктуре и каскадированию целей.\n"
            "Определи, соответствует ли строка 'Ответственный исполнитель' конкретному заместителю.\n"
            "В строке могут быть сокращения и ФИО в скобках, например: 'ДЦР (Пинчук Ю.В.)'.\n"
            "Верни строго JSON без пояснений:\n"
            '{"match": true|false, "confidence": 0..1, "reason": "кратко"}\n\n'
            f"Заместитель (эталон): {deputy_name}\n"
            f"Ответственный исполнитель (из стратегии): {responsible_executor}\n"
            f"Цель: {goal_title}\n"
            f"Инициатива: {initiative}\n"
        )
        parsed = self._ask_json_with_fallback(prompt, model=model)
        if not parsed:
            logger.warning(
                "LLM responsible match '%s' vs '%s': empty response (model=%s, elapsed=%.2fs)",
                deputy_name,
                responsible_executor,
                model,
                time.perf_counter() - started_at,
            )
            return None
        matched = bool(parsed.get("match"))
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = str(parsed.get("reason") or "").strip()
        logger.info(
            "LLM responsible match '%s' vs '%s': match=%s confidence=%.3f model=%s elapsed=%.2fs",
            deputy_name,
            responsible_executor,
            matched,
            confidence,
            model,
            time.perf_counter() - started_at,
        )
        return {"match": matched, "confidence": confidence, "reason": reason}

    def assess_goals_relevance_bulk(
        self,
        *,
        subject_name: str,
        process_names: list[str],
        goals: list[dict[str, str]],
        force: bool = False,
    ) -> Optional[dict[int, dict[str, object]]]:
        if not self.enabled and not force:
            return None
        if not process_names or not goals:
            return None
        model = getattr(settings, "cascade_llm_judge_model", "qwen3:8b")
        process_text = "\n".join(f"- {name}" for name in process_names[:30])
        goals_text = "\n".join(
            f"- idx={idx}; goal={g.get('sourceGoalTitle','')}; metric={g.get('sourceMetric','')}"
            for idx, g in enumerate(goals)
        )
        prompt = (
            "Ты эксперт по каскадированию KPI и процессному управлению.\n"
            "Для каждого кандидата цели оцени релевантность процессам сотрудника.\n"
            "Критерии строгости:\n"
            "1) relevant=true только при четком совпадении процесса и цели,\n"
            "   либо при частичном совпадении текста >= 50%.\n"
            "2) Совпадение по одному общему слову не считается релевантным.\n"
            "3) Если совпадение < 50% -> relevant=false.\n"
            "Верни строго JSON:\n"
            '{"items":[{"idx":0,"relevant":true,"confidence":0.0,"overlap":0.0,'
            '"matchType":"exact|partial|none","matchedProcess":"","reason":""}]}\n\n'
            f"Сотрудник: {subject_name}\n"
            f"Процессы сотрудника:\n{process_text}\n\n"
            f"Кандидаты целей:\n{goals_text}\n"
        )
        parsed = self._ask_json_with_fallback(prompt, model=model)
        if not isinstance(parsed, dict):
            return None
        raw_items = parsed.get("items")
        if not isinstance(raw_items, list):
            return None
        out: dict[int, dict[str, object]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("idx"))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(goals):
                continue
            relevant = bool(item.get("relevant"))
            try:
                confidence = float(item.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            reason = str(item.get("reason") or "").strip()
            out[idx] = {"relevant": relevant, "confidence": confidence, "reason": reason}
        return out or None

    def _ask_json_with_fallback(self, prompt: str, *, model: str) -> Optional[dict]:
        timeout = getattr(settings, "cascade_llm_timeout_sec", 35.0)
        messages = [{"role": "user", "content": prompt}]
        raw = chat_completion(
            messages,
            model=model,
            temperature=0.1,
            use_ollama=True,
            timeout=timeout,
        )
        parsed = _extract_json(raw or "")
        if isinstance(parsed, dict):
            return parsed

        fallback_model = str(getattr(settings, "cascade_llm_fallback_model", "") or "").strip()
        if not fallback_model or fallback_model == model:
            return None
        logger.warning("Primary LLM model '%s' failed, trying fallback '%s'", model, fallback_model)
        raw_fb = chat_completion(
            messages,
            model=fallback_model,
            temperature=0.1,
            use_ollama=True,
            timeout=timeout,
        )
        parsed_fb = _extract_json(raw_fb or "")
        return parsed_fb if isinstance(parsed_fb, dict) else None


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
