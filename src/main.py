import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from .api.routes import (
    board_goals,
    cascade,
    chat,
    collections,
    dashboard,
    db as db_router,
    documents,
    leader_goals,
    process_registry,
    reference,
    staff,
    settings as settings_router,
    strategy_goals,
)
from .core.config import settings
from .db.database import init_db


def _init_db_with_retry(max_attempts: int = 3, delay_sec: float = 1.5) -> None:
    """Пытается создать таблицы; при ошибке пробрасывает исключение (см. lifespan)."""
    import time

    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            init_db()
            return
        except Exception as e:
            last_exc = e
            if attempt < max_attempts:
                time.sleep(delay_sec)
    raise last_exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _init_db_with_retry()
    except Exception as e:
        logging.getLogger(__name__).warning(
            "БД недоступна при старте, таблицы не созданы: %s. "
            "Сервис всё равно запущен — откройте /docs и /health. "
            "Проверьте DATABASE_URL и что PostgreSQL запущен (см. README).",
            e,
        )
    # startup: MinIO — создать бакеты по типам документов при необходимости
    if settings.use_minio:
        try:
            from .services.file_storage import ensure_buckets_exist
            ensure_buckets_exist()
        except Exception:
            pass  # MinIO может быть ещё недоступен
    yield
    # shutdown
    pass


app = FastAPI(
    title="AI KPI API",
    description="API для автоматизированного каскадирования целей",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Чтобы при любой ошибке клиент получал JSON с detail, а не plain 'Internal Server Error'."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logging.getLogger(__name__).exception("Unhandled: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal Server Error"},
    )

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(collections.router, prefix="/api/collections", tags=["collections"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(cascade.router, prefix="/api/cascade", tags=["cascade"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(board_goals.router, prefix="/api/board-goals", tags=["board-goals"])
app.include_router(leader_goals.router, prefix="/api/leader-goals", tags=["leader-goals"])
app.include_router(strategy_goals.router, prefix="/api/strategy-goals", tags=["strategy-goals"])
app.include_router(process_registry.router, prefix="/api/process-registry", tags=["process-registry"])
app.include_router(staff.router, prefix="/api/staff", tags=["staff"])
app.include_router(reference.router, prefix="/api/reference", tags=["reference"])
app.include_router(db_router.router, prefix="/api/db", tags=["db"])


@app.get("/")
@app.get("/health")
def healthcheck():
    return {"status": "ok"}
