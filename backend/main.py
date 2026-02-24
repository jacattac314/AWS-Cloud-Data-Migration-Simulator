"""Cloud Migration Command Center – FastAPI backend entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.models.database import create_tables
from backend.routers import compliance, dashboard, demo, knowledge, migration


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables on startup."""
    create_tables()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "REST API for the Cloud Migration Command Center – "
        "migration planning, KLO knowledge search, compliance management, and executive metrics."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(migration.router)
app.include_router(knowledge.router)
app.include_router(compliance.router)
app.include_router(dashboard.router)
app.include_router(demo.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}
