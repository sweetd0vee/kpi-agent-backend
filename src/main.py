from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import (
    chat,
    collections,
    dashboard,
    db as db_router,
    departments,
    documents,
    leaders,
    kpi,
    ppr,
    reference,
    settings as settings_router,
)
from .core.config import settings
from .db.database import init_db


def _init_db_with_retry(max_attempts: int = 5, delay_sec: float = 2.0) -> None:
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
    _init_db_with_retry()
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

app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(collections.router, prefix="/api/collections", tags=["collections"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(kpi.router, prefix="/api/kpi", tags=["kpi"])
app.include_router(ppr.router, prefix="/api/ppr", tags=["ppr"])
app.include_router(reference.router, prefix="/api/reference", tags=["reference"])
app.include_router(departments.router, prefix="/api/departments", tags=["departments"])
app.include_router(leaders.router, prefix="/api/leaders", tags=["leaders"])
app.include_router(db_router.router, prefix="/api/db", tags=["db"])


@app.get("/")
@app.get("/health")
def healthcheck():
    return {"status": "ok"}
