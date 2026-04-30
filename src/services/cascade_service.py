"""Каскадирование KPI между manager -> deputy с фильтрацией по процессам."""

from __future__ import annotations

import logging
import random
import re
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from src.core.config import settings
from src.services.cascade_llm import CascadeLlmAdapter
from src.services.cascade_repository import CascadeSnapshot

logger = logging.getLogger(__name__)


def norm_text(value: object) -> str:
    text = str(value or "").strip().lower().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def normalize_name(value: object) -> str:
    text = norm_text(value)
    text = re.sub(r"[^a-zа-я0-9\s]", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def names_match(left: object, right: object) -> bool:
    a = normalize_name(left)
    b = normalize_name(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and a in b:
        return True
    if len(b) >= 6 and b in a:
        return True
    return False


@dataclass
class CascadeComputationResult:
    report_year: str
    selected_managers: list[str]
    total_managers: int
    total_deputies: int
    warnings: list[str]
    unmatched: list[dict[str, str]]
    items: list[dict[str, object]]
    fallback_goals: list[dict[str, str]]


class CascadeService:
    def __init__(self, snapshot: CascadeSnapshot) -> None:
        self.snapshot = snapshot
        self.llm = CascadeLlmAdapter()

    def run(
        self,
        *,
        report_year: str = "",
        managers: Optional[list[str]] = None,
        max_items_per_deputy: int = 25,
        use_llm: bool = False,
    ) -> CascadeComputationResult:
        started_at = time.perf_counter()
        manager_to_deputies = self._build_manager_tree()
        person_to_processes = self._build_manager_processes()
        person_to_business_units = self._build_person_business_units()
        selected = [m.strip() for m in (managers or []) if m and m.strip()]
        if not selected:
            selected = sorted(manager_to_deputies.keys())
        logger.info(
            "Cascade run started: managers=%s use_llm=%s report_year=%s max_per_deputy=unlimited (requested=%s)",
            len(selected),
            use_llm,
            report_year or "-",
            max_items_per_deputy,
        )

        all_deputies: set[str] = set()
        items: list[dict[str, object]] = []
        unmatched: list[dict[str, str]] = []
        fallback_goals: list[dict[str, str]] = []
        item_seen: set[tuple[str, str, str, str, str, str]] = set()
        fallback_seen: set[tuple[str, str, str, str, str, str]] = set()
        strategy_executor_match_cache: dict[tuple[str, str], tuple[bool, str]] = {}
        rng = random.Random()
        warnings: list[str] = []

        def append_not_found_item(deputy_name: str, reason: str) -> None:
            unique_key = (
                "",
                normalize_name(deputy_name),
                "not_found",
                "",
                norm_text("KPI не найдено"),
                norm_text(reason),
            )
            if unique_key in item_seen:
                return
            item_seen.add(unique_key)
            items.append(
                {
                    "id": str(uuid.uuid4()),
                    # По запросу: в поле фамилия (руководитель) оставляем пустое значение.
                    "managerName": "",
                    "deputyName": deputy_name,
                    "sourceType": "not_found",
                    "sourceRowId": "",
                    "sourceGoalTitle": "KPI не найдено",
                    "sourceMetric": "",
                    "businessUnit": "",
                    "department": "",
                    "reportYear": report_year,
                    "traceRule": reason,
                    "confidence": None,
                }
            )

        for manager_name in selected:
            manager_started = time.perf_counter()
            source_goals = self._build_source_goals_for_manager(manager_name, report_year=report_year)
            deputies = sorted(manager_to_deputies.get(manager_name, set()))
            assigned_goal_keys_for_manager: set[tuple[str, str, str, str]] = set()
            deputy_processes_map: dict[str, list[str]] = {}
            deputy_business_units_map: dict[str, list[str]] = {}
            deputy_strategy_goals_map: dict[str, list[dict[str, str]]] = {}
            if not deputies:
                reason = "В staff не найдены подчиненные по полю functionalBlockCurator."
                logger.info("Manager '%s': no deputies found in staff", manager_name)
                self._append_fallback_goals_for_manager(
                    manager_name=manager_name,
                    deputy_name="",
                    source_goals=source_goals,
                    reason=reason,
                    report_year=report_year,
                    rng=rng,
                    out=fallback_goals,
                    seen=fallback_seen,
                )
                continue
            if not source_goals:
                logger.info("Manager '%s': no source goals found", manager_name)
                continue
            manager_items_before = len(items)
            logger.info(
                "Manager '%s': deputies=%s source_goals=%s",
                manager_name,
                len(deputies),
                len(source_goals),
            )

            for deputy_name in deputies:
                all_deputies.add(deputy_name)
                deputy_processes = self._get_processes_for_person(person_to_processes, deputy_name)
                deputy_business_units = self._get_business_units_for_person(
                    person_to_business_units,
                    deputy_name,
                )
                deputy_processes_map[deputy_name] = deputy_processes
                deputy_business_units_map[deputy_name] = deputy_business_units
                llm_rejections: list[str] = []
                strategy_direct_goals = self._build_strategy_goals_for_deputy(
                    deputy_name=deputy_name,
                    report_year=report_year,
                    use_llm=use_llm,
                    match_cache=strategy_executor_match_cache,
                )
                deputy_strategy_goals_map[deputy_name] = strategy_direct_goals
                if not deputy_processes and not strategy_direct_goals:
                    reason = (
                        f"Для заместителя '{deputy_name}' не найдены процессы "
                        "в реестре процессов и цели в стратегии."
                    )
                    logger.info(
                        "Manager '%s' deputy '%s': no processes and no strategy goals",
                        manager_name,
                        deputy_name,
                    )
                    unmatched.append(
                        {
                            "managerName": manager_name,
                            "deputyName": deputy_name,
                            "reason": reason,
                            "reportYear": report_year,
                        }
                    )
                    append_not_found_item(deputy_name, reason)
                    self._append_fallback_goals_for_manager(
                        manager_name=manager_name,
                        deputy_name=deputy_name,
                        source_goals=source_goals,
                        reason=reason,
                        report_year=report_year,
                        rng=rng,
                        out=fallback_goals,
                        seen=fallback_seen,
                    )
                    continue
                deputy_goals = self._filter_goals_by_process_relevance(
                    subject_name=deputy_name,
                    process_names=deputy_processes,
                    deputy_business_units=deputy_business_units,
                    source_goals=source_goals,
                    use_llm=use_llm,
                    llm_rejections_out=llm_rejections,
                )
                if use_llm and strategy_direct_goals:
                    strategy_llm_rejections: list[str] = []
                    strategy_direct_goals = self._filter_goals_by_process_relevance(
                        subject_name=deputy_name,
                        process_names=deputy_processes,
                        deputy_business_units=deputy_business_units,
                        source_goals=strategy_direct_goals,
                        use_llm=True,
                        llm_rejections_out=strategy_llm_rejections,
                    )
                deputy_goals = self._merge_goal_candidates(deputy_goals, strategy_direct_goals)
                if not deputy_goals:
                    reason = (
                        "Не нашлось ни в реестре процессов, ни в стратегии."
                    )
                    logger.info(
                        "Manager '%s' deputy '%s': no relevant goals after filtering (processes=%s, strategy_direct=%s)",
                        manager_name,
                        deputy_name,
                        len(deputy_processes),
                        len(strategy_direct_goals),
                    )
                    append_not_found_item(deputy_name, reason)
                    self._append_fallback_goals_for_manager(
                        manager_name=manager_name,
                        deputy_name=deputy_name,
                        source_goals=source_goals,
                        reason=reason,
                        report_year=report_year,
                        rng=rng,
                        out=fallback_goals,
                        seen=fallback_seen,
                    )
                    continue
                logger.info(
                    "Manager '%s' deputy '%s': relevant_goals=%s (processes=%s, business_units=%s, strategy_direct=%s)",
                    manager_name,
                    deputy_name,
                    len(deputy_goals),
                    len(deputy_processes),
                    len(deputy_business_units),
                    len(strategy_direct_goals),
                )
                for source in deputy_goals:
                    source_type = str(source.get("sourceType") or "")
                    source_row_id = str(source.get("sourceRowId") or "")
                    source_goal_title = str(source.get("sourceGoalTitle") or "")
                    source_metric = str(source.get("sourceMetric") or "")
                    assigned_goal_keys_for_manager.add(
                        (
                            source_type,
                            source_row_id,
                            norm_text(source_goal_title),
                            norm_text(source_metric),
                        )
                    )
                    unique_key = (
                        normalize_name(manager_name),
                        normalize_name(deputy_name),
                        source_type,
                        source_row_id,
                        norm_text(source_goal_title),
                        norm_text(source_metric),
                    )
                    if unique_key in item_seen:
                        continue
                    item_seen.add(unique_key)
                    items.append(
                        {
                            "id": str(uuid.uuid4()),
                            "managerName": manager_name,
                            "deputyName": deputy_name,
                            "sourceType": source_type,
                            "sourceRowId": source_row_id,
                            "sourceGoalTitle": source_goal_title,
                            "sourceMetric": source_metric,
                            "businessUnit": source["businessUnit"],
                            "department": source["department"],
                            "reportYear": source["reportYear"] or report_year,
                            "traceRule": self._build_readable_trace(
                                manager_name=manager_name,
                                deputy_name=deputy_name,
                                source_type=source_type,
                                source_trace=str(source.get("traceRule") or ""),
                            ),
                            "confidence": (
                                float(source["confidence"])
                                if source.get("confidence") not in (None, "")
                                else None
                            ),
                        }
                    )

            # Нераспределенные board-цели показываем в итоговой таблице как цели
            # без назначения на заместителя (deputyName пустой).
            for source in source_goals:
                source_type = str(source.get("sourceType") or "")
                source_row_id = str(source.get("sourceRowId") or "")
                source_goal_title = str(source.get("sourceGoalTitle") or "")
                source_metric = str(source.get("sourceMetric") or "")
                goal_key = (
                    source_type,
                    source_row_id,
                    norm_text(source_goal_title),
                    norm_text(source_metric),
                )
                if goal_key in assigned_goal_keys_for_manager:
                    continue
                unique_key = (
                    normalize_name(manager_name),
                    "",
                    source_type or "unassigned",
                    source_row_id,
                    norm_text(source_goal_title),
                    norm_text(source_metric),
                )
                if unique_key in item_seen:
                    continue
                item_seen.add(unique_key)
                items.append(
                    {
                        "id": str(uuid.uuid4()),
                        "managerName": manager_name,
                        "deputyName": "",
                        "sourceType": source_type or "unassigned",
                        "sourceRowId": source_row_id,
                        "sourceGoalTitle": source_goal_title or "KPI не найдено",
                        "sourceMetric": source_metric,
                        "businessUnit": str(source.get("businessUnit") or ""),
                        "department": str(source.get("department") or ""),
                        "reportYear": str(source.get("reportYear") or report_year),
                        "traceRule": self._build_readable_trace(
                            manager_name=manager_name,
                            deputy_name="—",
                            source_type=source_type or "unassigned",
                            source_trace="Цель не была сопоставлена ни одному заместителю.",
                        ),
                        "confidence": None,
                    }
                )
            logger.info(
                "Manager '%s': finished in %.2fs, items_added=%s",
                manager_name,
                time.perf_counter() - manager_started,
                len(items) - manager_items_before,
            )

        if not items:
            warnings.append("Каскадирование не дало назначений. Проверьте заполненность staff и целей.")
        logger.info(
            "Cascade run finished in %.2fs: items=%s unmatched=%s fallback_goals=%s deputies=%s",
            time.perf_counter() - started_at,
            len(items),
            len(unmatched),
            len(fallback_goals),
            len(all_deputies),
        )

        return CascadeComputationResult(
            report_year=report_year,
            selected_managers=selected,
            total_managers=len(selected),
            total_deputies=len(all_deputies),
            warnings=warnings,
            unmatched=unmatched,
            items=items,
            fallback_goals=fallback_goals,
        )

    def _append_fallback_goals_for_manager(
        self,
        *,
        manager_name: str,
        deputy_name: str,
        source_goals: list[dict[str, str]],
        reason: str,
        report_year: str,
        rng: random.Random,
        out: list[dict[str, str]],
        seen: set[tuple[str, str, str, str, str, str]],
    ) -> None:
        if not source_goals:
            return
        random_goals = list(source_goals)
        rng.shuffle(random_goals)
        for source in random_goals:
            source_type = str(source.get("sourceType") or "")
            source_row_id = str(source.get("sourceRowId") or "")
            source_goal_title = str(source.get("sourceGoalTitle") or "")
            source_metric = str(source.get("sourceMetric") or "")
            unique_key = (
                normalize_name(manager_name),
                normalize_name(deputy_name),
                source_type,
                source_row_id,
                norm_text(source_goal_title),
                norm_text(source_metric),
            )
            if unique_key in seen:
                continue
            seen.add(unique_key)
            out.append(
                {
                    "id": str(uuid.uuid4()),
                    "managerName": manager_name,
                    "deputyName": deputy_name,
                    "sourceType": source_type,
                    "sourceRowId": source_row_id,
                    "sourceGoalTitle": source_goal_title,
                    "sourceMetric": source_metric,
                    "businessUnit": str(source.get("businessUnit") or ""),
                    "department": str(source.get("department") or ""),
                    "reportYear": str(source.get("reportYear") or report_year),
                    "reason": reason,
                }
            )

    def _build_manager_tree(self) -> dict[str, set[str]]:
        tree: dict[str, set[str]] = {}
        for row in self.snapshot.staff_rows:
            manager = str(row.functional_block_curator or "").strip()
            deputy = str(row.head or "").strip()
            if not manager or not deputy:
                continue
            if names_match(manager, deputy):
                continue
            tree.setdefault(manager, set()).add(deputy)
        return tree

    def _build_manager_processes(self) -> dict[str, list[str]]:
        processes: dict[str, list[str]] = {}
        for row in self.snapshot.process_rows:
            manager_name = str(row.leader or "").strip()
            process_name = str(row.process or "").strip()
            if not manager_name or not process_name:
                continue
            existing_key = next((key for key in processes if names_match(key, manager_name)), manager_name)
            processes.setdefault(existing_key, [])
            if process_name not in processes[existing_key]:
                processes[existing_key].append(process_name)
        return processes

    def _build_person_business_units(self) -> dict[str, list[str]]:
        units: dict[str, list[str]] = {}
        for row in self.snapshot.staff_rows:
            person_name = str(row.head or "").strip()
            if not person_name:
                continue
            values = [str(row.business_unit or "").strip(), str(row.unit_name or "").strip()]
            existing_key = next((key for key in units if names_match(key, person_name)), person_name)
            units.setdefault(existing_key, [])
            for value in values:
                if value and value not in units[existing_key]:
                    units[existing_key].append(value)
        return units

    def _get_processes_for_person(
        self,
        person_to_processes: dict[str, list[str]],
        person_name: str,
    ) -> list[str]:
        direct = person_to_processes.get(person_name)
        if direct:
            return direct
        for key, values in person_to_processes.items():
            if names_match(key, person_name):
                return values
        return []

    def _get_business_units_for_person(
        self,
        person_to_units: dict[str, list[str]],
        person_name: str,
    ) -> list[str]:
        direct = person_to_units.get(person_name)
        if direct:
            return direct
        for key, values in person_to_units.items():
            if names_match(key, person_name):
                return values
        return []

    def _filter_goals_by_process_relevance(
        self,
        *,
        subject_name: str,
        process_names: list[str],
        deputy_business_units: list[str],
        source_goals: list[dict[str, str]],
        use_llm: bool,
        llm_rejections_out: Optional[list[str]] = None,
    ) -> list[dict[str, str]]:
        filter_started = time.perf_counter()
        scored_candidates: list[dict[str, object]] = []
        for source in source_goals:
            goal_title = str(source.get("sourceGoalTitle") or "")
            goal_metric = str(source.get("sourceMetric") or "")
            goal_text = f"{goal_title} {goal_metric}".strip()
            if not goal_text:
                continue
            keyword_score = self._keyword_relevance_score(goal_text, process_names)
            business_score = self._business_unit_relevance_score(source, deputy_business_units)
            source_score = self._source_priority_score(str(source.get("sourceType") or ""))
            process_explain = self._build_process_match_explanation(goal_text, process_names)
            rule_score = (0.6 * keyword_score) + (0.3 * business_score) + (0.1 * source_score)
            source_type = norm_text(source.get("sourceType") or "")
            allow_strategy_llm_check = use_llm and source_type == "strategy"
            if rule_score < 0.12 and keyword_score <= 0 and business_score <= 0 and not allow_strategy_llm_check:
                continue
            scored_candidates.append(
                {
                    "source": source,
                    "rule_score": rule_score,
                    "keyword_score": keyword_score,
                    "business_score": business_score,
                    "source_score": source_score,
                    "process_explain": process_explain,
                }
            )

        if not scored_candidates:
            logger.info(
                "Relevance filter '%s': no rule candidates (source_goals=%s, processes=%s, business_units=%s)",
                subject_name,
                len(source_goals),
                len(process_names),
                len(deputy_business_units),
            )
            return []

        scored_candidates.sort(key=lambda x: float(x["rule_score"]), reverse=True)
        llm_limit = max(1, int(getattr(settings, "cascade_llm_max_candidates_per_deputy", 15)))
        llm_calls = 0

        llm_bulk_map: dict[int, dict[str, object]] = {}
        llm_candidates = [item["source"] for item in scored_candidates[:llm_limit]]
        if use_llm and llm_candidates:
            llm_calls = 1
            llm_bulk = self.llm.assess_goals_relevance_bulk(
                subject_name=subject_name,
                process_names=process_names,
                goals=llm_candidates,
                force=True,
            )
            if isinstance(llm_bulk, dict):
                llm_bulk_map = llm_bulk

        reranked: list[tuple[float, dict[str, str]]] = []
        for idx, candidate in enumerate(scored_candidates):
            source = candidate["source"]
            rule_score = float(candidate["rule_score"])
            keyword_score = float(candidate["keyword_score"])
            business_score = float(candidate["business_score"])
            source_score = float(candidate["source_score"])
            process_explain = str(candidate.get("process_explain") or "")
            goal_title = str(source.get("sourceGoalTitle") or "")
            goal_metric = str(source.get("sourceMetric") or "")

            llm_reason = ""
            llm_confidence: Optional[float] = None
            llm_relevant: Optional[bool] = None
            final_score = rule_score
            if use_llm and idx < llm_limit:
                llm_result = llm_bulk_map.get(idx)
                if llm_result is not None:
                    llm_relevant = bool(llm_result.get("relevant"))
                    llm_reason = str(llm_result.get("reason") or "").strip()
                    confidence_raw = llm_result.get("confidence")
                    try:
                        llm_confidence = float(confidence_raw) if confidence_raw is not None else None
                    except (TypeError, ValueError):
                        llm_confidence = None
                    if llm_confidence is not None:
                        llm_delta = (llm_confidence if llm_relevant else -llm_confidence) * 0.35
                        final_score = max(0.0, min(1.0, rule_score + llm_delta))

            if llm_relevant is False:
                rejection_reason = (
                    f"llm_relevant=False; goal='{goal_title[:120]}'; "
                    f"reason: {llm_reason or 'Судья отметил цель как нерелевантную'}"
                )
                if llm_rejections_out is not None:
                    llm_rejections_out.append(rejection_reason)
                logger.info("Relevance filter '%s': %s", subject_name, rejection_reason)
                continue

            trace = source.get("traceRule") or ""
            source_type = str(source.get("sourceType") or "")
            source_explain = self._source_priority_explanation(source_type)
            business_explain = self._business_unit_relevance_explanation(source, deputy_business_units)
            if use_llm:
                if idx < llm_limit:
                    trace = (
                        f"{trace}; score: rule={rule_score:.3f},final={final_score:.3f},"
                        f"keyword={keyword_score:.3f},business={business_score:.3f},source={source_score:.3f}; "
                        f"relevance: llm_rerank+process_registry({subject_name})"
                    )
                    if process_explain:
                        trace = f"{trace}; process_match: {process_explain}"
                    trace = f"{trace}; business_match: {business_explain}"
                    trace = f"{trace}; source_reason: {source_explain}"
                    trace = f"{trace}; classification: process_registry"
                    if llm_relevant is not None:
                        trace = f"{trace}; llm_relevant={llm_relevant}"
                    if llm_reason:
                        trace = f"{trace}; reason: {llm_reason}"
                else:
                    trace = (
                        f"{trace}; score: rule={rule_score:.3f},final={final_score:.3f},"
                        f"keyword={keyword_score:.3f},business={business_score:.3f},source={source_score:.3f}; "
                        f"relevance: rule_based+process_registry({subject_name}); llm: skipped_by_limit"
                    )
                    if process_explain:
                        trace = f"{trace}; process_match: {process_explain}"
                    trace = f"{trace}; business_match: {business_explain}"
                    trace = f"{trace}; source_reason: {source_explain}"
                    trace = f"{trace}; classification: process_registry"
            else:
                trace = (
                    f"{trace}; score: rule={rule_score:.3f},final={final_score:.3f},"
                    f"keyword={keyword_score:.3f},business={business_score:.3f},source={source_score:.3f}; "
                    f"relevance: rule_based+process_registry({subject_name})"
                )
                if process_explain:
                    trace = f"{trace}; process_match: {process_explain}"
                trace = f"{trace}; business_match: {business_explain}"
                trace = f"{trace}; source_reason: {source_explain}"
                trace = f"{trace}; classification: process_registry"

            item = {**source, "traceRule": trace}
            item["confidence"] = str(round(llm_confidence if llm_confidence is not None else final_score, 4))
            reranked.append((final_score, item))

        reranked.sort(key=lambda x: x[0], reverse=True)
        filtered = [item for _score, item in reranked]
        logger.info(
            "Relevance filter '%s': source=%s rule_candidates=%s filtered=%s llm_calls=%s llm_limit=%s elapsed=%.2fs",
            subject_name,
            len(source_goals),
            len(scored_candidates),
            len(filtered),
            llm_calls,
            llm_limit,
            time.perf_counter() - filter_started,
        )
        return filtered

    def _is_goal_relevant_by_keywords(self, goal_text: str, process_names: list[str]) -> bool:
        return self._keyword_relevance_score(goal_text, process_names) > 0

    def _keyword_relevance_score(self, goal_text: str, process_names: list[str]) -> float:
        goal_tokens = self._tokenize(goal_text)
        if not goal_tokens:
            return 0.0
        best_score = 0.0
        for process_name in process_names:
            process_tokens = self._tokenize(process_name)
            if not process_tokens:
                continue
            overlap = goal_tokens.intersection(process_tokens)
            if not overlap:
                continue
            score = len(overlap) / max(1, len(process_tokens))
            if score > best_score:
                best_score = score
        return best_score

    def _tokenize(self, text: str) -> set[str]:
        parts = re.split(r"[^a-zA-Zа-яА-Я0-9]+", norm_text(text))
        return {part for part in parts if len(part) >= 3}

    def _business_unit_relevance_score(
        self,
        source: dict[str, str],
        deputy_business_units: list[str],
    ) -> float:
        if not deputy_business_units:
            return 0.0
        source_units = [
            str(source.get("businessUnit") or "").strip(),
            str(source.get("department") or "").strip(),
        ]
        source_units = [value for value in source_units if value]
        if not source_units:
            return 0.0

        deputy_norm = {norm_text(value) for value in deputy_business_units if value}
        source_norm = {norm_text(value) for value in source_units if value}
        if deputy_norm.intersection(source_norm):
            return 1.0

        deputy_tokens: set[str] = set()
        source_tokens: set[str] = set()
        for value in deputy_norm:
            deputy_tokens.update(self._tokenize(value))
        for value in source_norm:
            source_tokens.update(self._tokenize(value))
        overlap = deputy_tokens.intersection(source_tokens)
        if not overlap:
            return 0.0
        return min(0.8, len(overlap) / max(1, len(source_tokens)))

    def _source_priority_score(self, source_type: str) -> float:
        source = norm_text(source_type)
        if source == "strategy":
            return 1.0
        if source == "board":
            return 0.75
        if source == "leader":
            return 0.65
        return 0.5

    def _source_priority_explanation(self, source_type: str) -> str:
        source = norm_text(source_type)
        if source == "strategy":
            return "strategy имеет повышенный приоритет (1.00)"
        if source == "board":
            return "board имеет высокий приоритет (0.75)"
        if source == "leader":
            return "leader имеет базовый приоритет (0.65)"
        return f"{source_type or 'unknown'} имеет стандартный приоритет (0.50)"

    def _build_process_match_explanation(self, goal_text: str, process_names: list[str]) -> str:
        goal_tokens = self._tokenize(goal_text)
        if not goal_tokens or not process_names:
            return ""
        best_parts: list[str] = []
        for process_name in process_names:
            process_tokens = self._tokenize(process_name)
            if not process_tokens:
                continue
            overlap = goal_tokens.intersection(process_tokens)
            if not overlap:
                continue
            ratio = len(overlap) / max(1, len(process_tokens))
            overlap_tokens = ",".join(sorted(overlap)[:4])
            best_parts.append(
                f"{process_name} (совпадение={ratio:.2f}; токены={overlap_tokens})"
            )
        if not best_parts:
            return "ключевые токены процессов не совпали"
        return " | ".join(best_parts[:2])

    def _business_unit_relevance_explanation(
        self,
        source: dict[str, str],
        deputy_business_units: list[str],
    ) -> str:
        if not deputy_business_units:
            return "у заместителя не найден бизнес-блок в staff"
        source_units = [
            str(source.get("businessUnit") or "").strip(),
            str(source.get("department") or "").strip(),
        ]
        source_units = [value for value in source_units if value]
        if not source_units:
            return "в цели не указан businessUnit/department"
        deputy_norm = {norm_text(value) for value in deputy_business_units if value}
        source_norm = {norm_text(value) for value in source_units if value}
        direct = deputy_norm.intersection(source_norm)
        if direct:
            return f"прямое совпадение блока/департамента: {', '.join(sorted(direct)[:2])}"
        return (
            f"прямого совпадения нет; deputy={', '.join(deputy_business_units[:2])}; "
            f"source={', '.join(source_units[:2])}"
        )

    def _build_source_goals_for_manager(self, manager_name: str, report_year: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        year = (report_year or "").strip()
        for row in self.snapshot.board_rows:
            if year and str(row.report_year or "").strip() != year:
                continue
            if not names_match(row.last_name, manager_name):
                continue
            out.append(
                {
                    "sourceType": "board",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": str(row.goal or ""),
                    "sourceMetric": str(row.metric_goals or ""),
                    "businessUnit": str(row.business_unit or ""),
                    "department": str(row.department or ""),
                    "reportYear": str(row.report_year or ""),
                    "traceRule": "match: board_goals.last_name == manager",
                }
            )

        return out

    def _build_readable_trace(
        self,
        *,
        manager_name: str,
        deputy_name: str,
        source_type: str,
        source_trace: str,
    ) -> str:
        readable = (
            f"Назначено от руководителя '{manager_name}' заместителю '{deputy_name}'. "
            f"Источник цели: '{source_type or 'unknown'}'."
        )
        trace = str(source_trace or "").strip()
        if not trace:
            return readable
        return f"{readable} {trace}"

    def _build_strategy_goals_for_deputy(
        self,
        *,
        deputy_name: str,
        report_year: str,
        use_llm: bool,
        match_cache: dict[tuple[str, str], tuple[bool, str]],
    ) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        year = (report_year or "").strip()
        for row in self.snapshot.strategy_rows:
            responsible_executor = str(row.responsible_person_owner or "")
            match_ok, match_trace = self._strategy_executor_matches_deputy(
                deputy_name=deputy_name,
                responsible_executor=responsible_executor,
                goal_title=str(row.goal_objective or ""),
                initiative=str(row.initiative or ""),
                use_llm=use_llm,
                cache=match_cache,
            )
            if not match_ok:
                continue
            out.append(
                {
                    "sourceType": "strategy",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": self._compose_strategy_title(
                        str(row.goal_objective or ""),
                        str(row.initiative or ""),
                    ),
                    "sourceMetric": str(row.kpi or ""),
                    "businessUnit": str(row.business_unit or ""),
                    "department": str(row.segment or ""),
                    "reportYear": year,
                    "traceRule": (
                        "match: strategy_goals.responsible_person_owner ~= deputy; "
                        f"responsible_executor='{responsible_executor}'; deputy='{deputy_name}'; "
                        f"{match_trace}; "
                        f"strategy_context: segment='{str(row.segment or '')}', initiative_type='{str(row.initiative_type or '')}'; "
                        "classification: strategy"
                    ),
                }
            )
        return out

    def _strategy_executor_matches_deputy(
        self,
        *,
        deputy_name: str,
        responsible_executor: str,
        goal_title: str,
        initiative: str,
        use_llm: bool,
        cache: dict[tuple[str, str], tuple[bool, str]],
    ) -> tuple[bool, str]:
        deputy = str(deputy_name or "").strip()
        executor_raw = str(responsible_executor or "").strip()
        if not deputy or not executor_raw:
            return False, "responsible_empty"

        if names_match(executor_raw, deputy):
            return True, "responsible: direct_name_match"

        candidates = self._extract_possible_person_names(executor_raw)
        if any(names_match(candidate, deputy) for candidate in candidates):
            return True, "responsible: parsed_name_match"

        key = (norm_text(executor_raw), normalize_name(deputy))
        if key in cache:
            cached_ok, cached_trace = cache[key]
            return cached_ok, cached_trace

        if not use_llm:
            cache[key] = (False, "responsible: llm_disabled")
            return False, "responsible: llm_disabled"

        deputy_tokens = [token for token in self._name_tokens(deputy) if len(token) >= 4]
        executor_norm = norm_text(executor_raw)
        if deputy_tokens and not any(token in executor_norm for token in deputy_tokens):
            cache[key] = (False, "responsible: token_prefilter_no_match")
            return False, "responsible: token_prefilter_no_match"

        llm_match = self.llm.assess_responsible_executor_match(
            deputy_name=deputy,
            responsible_executor=executor_raw,
            goal_title=goal_title,
            initiative=initiative,
            force=True,
        )
        if not llm_match:
            cache[key] = (False, "responsible: llm_empty")
            return False, "responsible: llm_empty"

        is_match = bool(llm_match.get("match"))
        reason = str(llm_match.get("reason") or "").strip()
        trace = "responsible: llm_match"
        if reason:
            trace = f"{trace}; reason: {reason}"
        cache[key] = (is_match, trace if is_match else "responsible: llm_no_match")
        return cache[key]

    def _extract_possible_person_names(self, text: str) -> list[str]:
        raw = str(text or "")
        candidates: list[str] = []

        in_brackets = re.findall(r"\(([^()]*)\)", raw)
        chunks = [raw, *in_brackets]
        splitter = re.compile(r"[,;/|]| и |\\n", flags=re.IGNORECASE)
        for chunk in chunks:
            for part in splitter.split(chunk):
                part = part.strip()
                if not part:
                    continue
                if re.search(r"[А-ЯЁ][а-яё-]+\s+[А-ЯЁ]\.[А-ЯЁ]\.", part):
                    candidates.append(part)
                elif re.search(r"[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+(?:\s+[А-ЯЁ][а-яё-]+)?", part):
                    candidates.append(part)

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = normalize_name(candidate)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _name_tokens(self, text: str) -> list[str]:
        return [token for token in re.split(r"[^a-zA-Zа-яА-Я0-9]+", norm_text(text)) if token]

    def _compose_strategy_title(self, goal_objective: str, initiative: str) -> str:
        goal = str(goal_objective or "").strip()
        init = str(initiative or "").strip()
        if goal and init:
            return f"{goal}. Инициатива: {init}"
        return goal or init

    def _merge_goal_candidates(
        self,
        primary: list[dict[str, str]],
        secondary: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        seen_index: dict[tuple[str, str, str, str], int] = {}
        for source in [*primary, *secondary]:
            key = (
                str(source.get("sourceType") or ""),
                str(source.get("sourceRowId") or ""),
                norm_text(str(source.get("sourceGoalTitle") or "")),
                norm_text(str(source.get("sourceMetric") or "")),
            )
            if key in seen_index:
                idx = seen_index[key]
                existing_trace = str(out[idx].get("traceRule") or "")
                incoming_trace = str(source.get("traceRule") or "")
                has_process = (
                    "classification: process_registry" in existing_trace
                    or "classification: process_registry" in incoming_trace
                    or "classification: strategy+process_registry" in existing_trace
                    or "classification: strategy+process_registry" in incoming_trace
                )
                has_strategy = (
                    "classification: strategy" in existing_trace
                    or "classification: strategy" in incoming_trace
                    or "classification: strategy+process_registry" in existing_trace
                    or "classification: strategy+process_registry" in incoming_trace
                )
                if has_process and has_strategy and "classification: strategy+process_registry" not in existing_trace:
                    updated_trace = existing_trace.replace(
                        "classification: process_registry",
                        "classification: strategy+process_registry",
                    ).replace(
                        "classification: strategy",
                        "classification: strategy+process_registry",
                    )
                    out[idx]["traceRule"] = updated_trace
                continue
            seen_index[key] = len(out)
            out.append(source)
        return out
