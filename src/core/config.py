from pydantic_settings import BaseSettings


# Соответствие типа документа бакету MinIO (каждый тип — свой бакет)
DOCUMENT_TYPE_TO_BUCKET = {
    "chairman_goals": "goals",
    "strategy_checklist": "strategy",
    "reglament_checklist": "regulation",
    "department_goals_checklist": "department-regulation",
    "business_plan_checklist": "business-plan",
    "goals_table": "goals",
}


class Settings(BaseSettings):
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    open_webui_url: str = "http://localhost:3000"
    open_webui_api_key: str = ""
    # Модель для чата (Open Web UI / OpenAI).
    llm_chat_model: str = "gpt-4o-mini"
    # Модель для каскадирования/итоговой таблицы (Open Web UI / OpenAI).
    llm_cascade_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    # Для предобработки документов (положение о департаменте, чеклисты): True = использовать Ollama, False = Open Web UI / OpenAI
    use_ollama_for_preprocess: bool = True
    # Модель Ollama для предобработки (должна быть запущена: ollama pull <model>).
    # Для положения о департаменте лучше быстрая модель 7B–8B (qwen3:8b, llama3.2); 70B очень долго.
    ollama_preprocess_model: str = "qwen3:8b"
    # Таймаут запроса к Ollama при предобработке (секунды). Увеличьте для больших моделей (70B).
    ollama_preprocess_timeout: float = 180.0
    # Для каскада: использовать Ollama вместо Open Web UI / OpenAI.
    use_ollama_for_cascade: bool = False
    # Модель Ollama для каскада (сильная). Должна быть установлена: ollama pull <model>.
    ollama_cascade_model: str = "qwen2.5:32b"
    # Таймаут запроса к Ollama при каскаде (секунды).
    ollama_cascade_timeout: float = 300.0
    upload_dir: str = "uploads"  # каталог для загруженных файлов базы знаний
    database_url: str = "postgresql+psycopg://postgres:postgres@db:5432/ai-kpi"

    # MinIO (S3-совместимое хранилище)
    use_minio: bool = False
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_use_ssl: bool = False

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False


settings = Settings()
