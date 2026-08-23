import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.imports import router as imports_router
from app.services.scheduler import start_scheduler

# Désactivé par défaut (dev/tests) : pas d'appel réseau planifié sans action
# explicite. Mettre ENABLE_INJURY_SCHEDULER=true pour l'activer (ex: run
# local pendant la saison).
ENABLE_INJURY_SCHEDULER = os.getenv("ENABLE_INJURY_SCHEDULER", "false").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler() if ENABLE_INJURY_SCHEDULER else None
    yield
    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title="Moteur de Pronostics NBA", lifespan=lifespan)

app.include_router(imports_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
