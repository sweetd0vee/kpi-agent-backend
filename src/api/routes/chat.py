"""
Чат с LLM и сценарий каскадирования (LangGraph).
По ТЗ: промпт + вложения (id документов/файлов) → LLM; опционально граф каскадирования.
"""
from fastapi import APIRouter, HTTPException

from src.models.chat import ChatRequest, ChatResponse, CascadeRequest, CascadeResponse

router = APIRouter()


@router.post("/completions", response_model=ChatResponse)
async def chat_completions(request: ChatRequest):
    """
    Запрос к LLM с контекстом (сообщения + прикреплённые документы по id).
    Может проксировать в Open Web UI или вызывать LangChain/LangGraph локально.
    """
    # TODO: вызов LLM (Open Web UI API или LangChain), передача file_ids как контекст
    raise HTTPException(status_code=501, detail="Реализация в разработке")


@router.post("/cascade", response_model=CascadeResponse)
async def run_cascade(request: CascadeRequest):
    """
    Запуск сценария каскадирования целей (LangGraph).
    Вход: файлы/цели руководителя, чеклисты; выход: структурированные цели по подразделениям.
    """
    # TODO: вызов графа LangGraph (graphs.cascade), возврат структурированного результата
    raise HTTPException(status_code=501, detail="Реализация в разработке")
