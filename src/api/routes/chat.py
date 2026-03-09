"""
Чат с LLM и сценарий каскадирования (LangGraph).
По ТЗ: промпт + вложения (id документов/файлов) → LLM; опционально граф каскадирования.
"""
import logging
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from src.core.config import settings
from src.models.chat import (
    CascadeRequest,
    CascadeResponse,
    ChatRequest,
    ChatResponse,
    ExportGoalsRequest,
)
from src.services.chat_context import get_documents_combined_text
from src.services.goal_export import export_goals_xlsx_from_llm_response
from src.services.llm import chat_completion

logger = logging.getLogger(__name__)
router = APIRouter()


def _messages_to_llm_format(messages: list) -> list[dict[str, str]]:
    return [{"role": m.role, "content": m.content} for m in messages]


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    """
    Запрос к LLM с контекстом (сообщения + прикреплённые документы по id).
    Контекст документов подставляется в системный промпт.
    """
    try:
        from kpi_agent_core import CHAT_SYSTEM_PROMPT
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Модуль kpi-agent-core не установлен. Выполните: pip install -e ../kpi-agent-core",
        )
    context_parts = []
    if request.file_ids:
        context_text = get_documents_combined_text(request.file_ids)
        if context_text:
            context_parts.append("Контекст из прикреплённых документов:\n\n" + context_text)
    system_content = CHAT_SYSTEM_PROMPT
    if context_parts:
        system_content = system_content + "\n\n" + "\n\n".join(context_parts)
    messages = [{"role": "system", "content": system_content}]
    for m in request.messages:
        messages.append({"role": m.role, "content": m.content})
    model = request.model or settings.llm_chat_model
    content = chat_completion(messages, model=model, temperature=0.2)
    if content is None:
        raise HTTPException(
            status_code=503,
            detail="Не удалось получить ответ от LLM. Проверьте настройки Open Web UI (OPEN_WEBUI_URL, OPEN_WEBUI_API_KEY).",
        )
    return ChatResponse(content=content, model=model)


@router.post("/cascade", response_model=CascadeResponse)
async def run_cascade(request: CascadeRequest):
    """
    Запуск сценария каскадирования целей (LangGraph).
    Вход: goal_file_ids, checklist_file_ids, context (опционально subdivisions).
    Выход: цели по подразделениям для дашборда.
    """
    try:
        from kpi_agent_core import build_cascade_graph
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Модуль kpi-agent-core не установлен. Выполните: pip install -e ../kpi-agent-core",
        )
    goals_text = get_documents_combined_text(request.goal_file_ids) if request.goal_file_ids else ""
    checklists_text = (
        get_documents_combined_text(request.checklist_file_ids) if request.checklist_file_ids else ""
    )
    if not goals_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Укажите хотя бы один документ с целями (goal_file_ids).",
        )
    context = request.context or {}
    if isinstance(context, dict) and "subdivisions" in context:
        context = {"subdivisions": list(context["subdivisions"])}
    else:
        context = {}

    use_ollama = getattr(settings, "use_ollama_for_cascade", False)
    model = settings.ollama_cascade_model if use_ollama else settings.llm_cascade_model
    timeout = settings.ollama_cascade_timeout if use_ollama else None

    def invoke_llm(messages: list[dict]) -> str:
        out = chat_completion(
            messages,
            model=model,
            temperature=0.1,
            use_ollama=use_ollama,
            timeout=timeout,
        )
        return out or ""

    graph = build_cascade_graph(invoke_llm)
    state = {
        "goals_text": goals_text,
        "checklists_text": checklists_text,
        "context": context,
    }
    try:
        result = graph.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка выполнения графа каскада: {e}") from e
    goals_by_subdivision = result.get("subdivision_goals") or []
    if result.get("error"):
        raise HTTPException(
            status_code=422,
            detail=f"Ошибка в шаге каскада: {result['error']}",
        )
    return CascadeResponse(
        goals_by_subdivision=goals_by_subdivision,
        raw_output=result.get("raw_output"),
    )


@router.post("/export-goals")
async def export_goals(request: ExportGoalsRequest):
    """
    Извлечь из текста ответа LLM таблицу целей (РАЗДЕЛ 8) и вернуть xlsx.
    Тело: { "content": "..." }. Ответ: файл цели_YYYYMMDD.xlsx или 404, если таблица не найдена.
    """
    try:
        content = request.content if request.content is not None else ""
        xlsx_bytes = export_goals_xlsx_from_llm_response(content)
        if xlsx_bytes is None:
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "В тексте не найдена таблица целей (РАЗДЕЛ 8 / CSV с разделителем «;»). Убедитесь, что модель вывела таблицу по шаблону."
                },
            )
        if not isinstance(xlsx_bytes, bytes):
            xlsx_bytes = bytes(xlsx_bytes) if xlsx_bytes else b""
        # Имя файла только ASCII, чтобы не ломать кодировку заголовков (latin-1)
        filename_ascii = f"goals_{date.today().strftime('%Y%m%d')}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename_ascii}"'},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("export-goals: %s", e)
        detail = str(e) if e else "Unknown error"
        return JSONResponse(
            status_code=500,
            content={"detail": f"Ошибка при формировании xlsx: {detail}"},
        )
