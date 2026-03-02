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
    ollama_base_url: str = "http://localhost:11434"
    upload_dir: str = "uploads"  # каталог для загруженных файлов базы знаний

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
