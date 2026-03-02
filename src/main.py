from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import chat, collections, dashboard, documents
from .core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])


@app.get("/")
@app.get("/health")
def healthcheck():
    return {"status": "ok"}
