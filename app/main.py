import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from app.logging_config import setup_logging  # noqa: E402

setup_logging()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from app.api.auth import router as auth_router  # noqa: E402
from app.api.games import router as games_router  # noqa: E402
from app.api.imports import router as imports_router  # noqa: E402
from app.api.players import router as players_router  # noqa: E402
from app.api.predictions import router as predictions_router  # noqa: E402
from app.api.settings import router as settings_router  # noqa: E402
from app.api.teams import router as teams_router  # noqa: E402
from app.services.scheduler import start_scheduler  # noqa: E402

# Désactivés par défaut (dev/tests) : pas d'appel réseau planifié sans action
# explicite. Mettre ENABLE_INJURY_SCHEDULER / ENABLE_SCORES_SCHEDULER à true
# pour les activer (ex: run local pendant la saison) -- indépendants l'un de
# l'autre, chacun n'enregistre que sa propre tâche (voir app/services/scheduler.py).
ENABLE_INJURY_SCHEDULER = os.getenv("ENABLE_INJURY_SCHEDULER", "false").lower() == "true"
ENABLE_SCORES_SCHEDULER = os.getenv("ENABLE_SCORES_SCHEDULER", "false").lower() == "true"

# Origines autorisées pour le frontend Vue.js (Vite). Ajustable via .env sans
# toucher au code (ex: une fois le port/domaine de l'Étape 5 confirmé).
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_scheduler() if (ENABLE_INJURY_SCHEDULER or ENABLE_SCORES_SCHEDULER) else None
    yield
    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title="Moteur de Pronostics NBA", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(imports_router)
app.include_router(settings_router)
app.include_router(predictions_router)
app.include_router(games_router)
app.include_router(players_router)
app.include_router(teams_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
