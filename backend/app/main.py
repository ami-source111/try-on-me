import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, health, sessions, tryon

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Миграции запускаются в entrypoint.sh ДО uvicorn
    logger.info("✅ App started")
    yield
    logger.info("App shutting down")


app = FastAPI(
    title="Try on Me API",
    version="2.0.0",
    description="Virtual try-on — cookie-based sessions, no auth required",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(tryon.router)
app.include_router(auth.router)
