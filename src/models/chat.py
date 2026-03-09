from typing import Dict, List, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str  # user | assistant | system
    content: str


class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    file_ids: List[str] = []


class ChatResponse(BaseModel):
    content: str
    model: Optional[str] = None


class CascadeRequest(BaseModel):
    """Вход сценария каскадирования: цели, чеклисты, контекст."""
    goal_file_ids: List[str] = []
    checklist_file_ids: List[str] = []
    context: Optional[Dict] = None


class CascadeResponse(BaseModel):
    """Структурированный результат: цели по подразделениям для дашборда."""
    goals_by_subdivision: List[dict]
    raw_output: Optional[str] = None


class ExportGoalsRequest(BaseModel):
    """Текст ответа LLM (например, последнее сообщение ассистента) для извлечения таблицы целей."""
    content: Optional[str] = ""
