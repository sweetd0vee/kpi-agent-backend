from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    open_webui_url: str = "http://localhost:3000"
    open_webui_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    upload_dir: str = "uploads"  # каталог для загруженных файлов базы знаний

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False


settings = Settings()
