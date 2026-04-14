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
        selected = [m.strip() for m in (managers or []) if m and m.strip()]
        if not selected:
            selected = sorted(manager_to_deputies.keys())
        max_per_deputy = max(1, min(max_items_per_deputy, 200))
        logger.info(
            "Cascade run started: managers=%s use_llm=%s report_year=%s max_per_deputy=%s",
            len(selected),
            use_llm,
            report_year or "-",
            max_per_deputy,
        )

        all_deputies: set[str] = set()
        items: list[dict[str, object]] = []
        unmatched: list[dict[str, str]] = []
        fallback_goals: list[dict[str, str]] = []
        item_seen: set[tuple[str, str, str, str, str, str]] = set()
        fallback_seen: set[tuple[str, str, str, str, str, str]] = set()
        rng = random.Random()
        warnings: list[str] = []

        for manager_name in selected:
            manager_started = time.perf_counter()
            source_goals = self._build_source_goals_for_manager(manager_name, report_year=report_year)
            deputies = sorted(manager_to_deputies.get(manager_name, set()))
            if not deputies:
                reason = "В staff не найдены подчиненные по полю functionalBlockCurator."
                logger.info("Manager '%s': no deputies found in staff", manager_name)
                unmatched.append(
                    {
                        "managerName": manager_name,
                        "reason": reason,
                        "reportYear": report_year,
                    }
                )
                self._append_fallback_goals_for_manager(
                    manager_name=manager_name,
                    deputy_name="",
                    source_goals=source_goals,
                    reason=reason,
                    report_year=report_year,
                    max_items=max_per_deputy,
                    rng=rng,
                    out=fallback_goals,
                    seen=fallback_seen,
                )
                continue
            if not source_goals:
                logger.info("Manager '%s': no source goals found", manager_name)
                unmatched.append(
                    {
                        "managerName": manager_name,
                        "reason": "Не найдены цели в таблицах board/leader/strategy для выбранного руководителя.",
                        "reportYear": report_year,
                    }
                )
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
                if not deputy_processes:
                    reason = f"Для заместителя '{deputy_name}' не найдены процессы в реестре процессов."
                    logger.info(
                        "Manager '%s' deputy '%s': no processes in registry",
                        manager_name,
                        deputy_name,
                    )
                    unmatched.append(
                        {
                            "managerName": manager_name,
                            "reason": reason,
                            "reportYear": report_year,
                        }
                    )
                    self._append_fallback_goals_for_manager(
                        manager_name=manager_name,
                        deputy_name=deputy_name,
                        source_goals=source_goals,
                        reason=reason,
                        report_year=report_year,
                        max_items=max_per_deputy,
                        rng=rng,
                        out=fallback_goals,
                        seen=fallback_seen,
                    )
                    continue
                deputy_goals = self._filter_goals_by_process_relevance(
                    subject_name=deputy_name,
                    process_names=deputy_processes,
                    source_goals=source_goals,
                    use_llm=use_llm,
                )
                if not deputy_goals:
                    reason = f"Для заместителя '{deputy_name}' не найдено релевантных целей по его процессам."
                    logger.info(
                        "Manager '%s' deputy '%s': no relevant goals after filtering (processes=%s)",
                        manager_name,
                        deputy_name,
                        len(deputy_processes),
                    )
                    unmatched.append(
                        {
                            "managerName": manager_name,
                            "reason": reason,
                            "reportYear": report_year,
                        }
                    )
                    self._append_fallback_goals_for_manager(
                        manager_name=manager_name,
                        deputy_name=deputy_name,
                        source_goals=source_goals,
                        reason=reason,
                        report_year=report_year,
                        max_items=max_per_deputy,
                        rng=rng,
                        out=fallback_goals,
                        seen=fallback_seen,
                    )
                    continue
                logger.info(
                    "Manager '%s' deputy '%s': relevant_goals=%s (processes=%s)",
                    manager_name,
                    deputy_name,
                    len(deputy_goals),
                    len(deputy_processes),
                )
                for source in deputy_goals[:max_per_deputy]:
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
                            "traceRule": source["traceRule"],
                            "confidence": (
                                float(source["confidence"])
                                if source.get("confidence") not in (None, "")
                                else None
                            ),
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
        max_items: int,
        rng: random.Random,
        out: list[dict[str, str]],
        seen: set[tuple[str, str, str, str, str, str]],
    ) -> None:
        if not source_goals:
            return
        random_goals = list(source_goals)
        rng.shuffle(random_goals)
        for source in random_goals[: max(1, min(max_items, len(random_goals)))]:
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

    def _filter_goals_by_process_relevance(
        self,
        *,
        subject_name: str,
        process_names: list[str],
        source_goals: list[dict[str, str]],
        use_llm: bool,
    ) -> list[dict[str, str]]:
        filter_started = time.perf_counter()
        scored_candidates: list[tuple[float, dict[str, str]]] = []
        for source in source_goals:
            goal_title = str(source.get("sourceGoalTitle") or "")
            goal_metric = str(source.get("sourceMetric") or "")
            goal_text = f"{goal_title} {goal_metric}".strip()
            if not goal_text:
                continue
            score = self._keyword_relevance_score(goal_text, process_names)
            if score <= 0:
                continue
            scored_candidates.append((score, source))

        if not scored_candidates:
            logger.info(
                "Relevance filter '%s': no keyword candidates (source_goals=%s, processes=%s)",
                subject_name,
                len(source_goals),
                len(process_names),
            )
            return []

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        llm_limit = max(1, int(getattr(settings, "cascade_llm_max_candidates_per_deputy", 15)))
        llm_calls = 0
        llm_cache_hits = 0

        llm_bulk_map: dict[int, dict[str, object]] = {}
        llm_candidates = [source for _, source in scored_candidates[:llm_limit]]
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

        filtered: list[dict[str, str]] = []
        for idx, (_score, source) in enumerate(scored_candidates):
            goal_title = str(source.get("sourceGoalTitle") or "")
            goal_metric = str(source.get("sourceMetric") or "")

            relevant = True  # keyword prefilter уже выполнен выше
            llm_reason = ""
            llm_confidence: Optional[float] = None
            if use_llm and idx < llm_limit:
                llm_result = llm_bulk_map.get(idx)
                if llm_result is not None:
                    relevant = bool(llm_result.get("relevant"))
                    llm_reason = str(llm_result.get("reason") or "").strip()
                    confidence_raw = llm_result.get("confidence")
                    try:
                        llm_confidence = float(confidence_raw) if confidence_raw is not None else None
                    except (TypeError, ValueError):
                        llm_confidence = None
            if not relevant:
                continue

            trace = source.get("traceRule") or ""
            if use_llm:
                if idx < llm_limit:
                    trace = f"{trace}; relevance: llm+process_registry({subject_name})"
                    if llm_reason:
                        trace = f"{trace}; reason: {llm_reason}"
                else:
                    trace = f"{trace}; relevance: keyword+process_registry({subject_name}); llm: skipped_by_limit"
            else:
                trace = f"{trace}; relevance: keyword+process_registry({subject_name})"

            item = {**source, "traceRule": trace}
            if llm_confidence is not None:
                item["confidence"] = str(round(llm_confidence, 4))
            filtered.append(item)
        logger.info(
            "Relevance filter '%s': source=%s keyword_candidates=%s filtered=%s llm_calls=%s llm_cache_hits=%s llm_limit=%s elapsed=%.2fs",
            subject_name,
            len(source_goals),
            len(scored_candidates),
            len(filtered),
            llm_calls,
            llm_cache_hits,
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

    def _build_source_goals_for_manager(self, manager_name: str, report_year: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        year = (report_year or "").strip()
        for row in self.snapshot.leader_rows:
            if year and str(row.report_year or "").strip() != year:
                continue
            if not names_match(row.last_name, manager_name):
                continue
            out.append(
                {
                    "sourceType": "leader",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": str(row.name or ""),
                    "sourceMetric": str(row.year_value or ""),
                    "businessUnit": "",
                    "department": "",
                    "reportYear": str(row.report_year or ""),
                    "traceRule": "match: leader_goals.last_name == manager",
                }
            )

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

        for row in self.snapshot.strategy_rows:
            if not names_match(row.responsible_person_owner, manager_name):
                continue
            out.append(
                {
                    "sourceType": "strategy",
                    "sourceRowId": row.id,
                    "sourceGoalTitle": str(row.goal_objective or row.initiative or ""),
                    "sourceMetric": str(row.kpi or ""),
                    "businessUnit": str(row.business_unit or ""),
                    "department": str(row.segment or ""),
                    "reportYear": year,
                    "traceRule": "match: strategy_goals.responsible_person_owner == manager",
                }
            )

        return out
