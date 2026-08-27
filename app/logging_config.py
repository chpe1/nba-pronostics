"""Configuration centralisée du logging applicatif.

Attache un RotatingFileHandler (fichier) + un StreamHandler (console) au
logger racine, pour que tous les loggers du projet (app.services.scheduler,
app.services.scores_fetcher, etc.) soient capturés automatiquement par
propagation, sans câblage par module.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
DEFAULT_LOG_FILE = LOG_DIR / "app.log"

# Usage perso, faible volume (deux jobs planifiés, quelques lignes par
# passage, tracebacks occasionnelles en cas d'échec réseau) : 1 Mo x 5
# fichiers de secours (~6 Mo au total) couvre largement plusieurs semaines
# à plusieurs mois d'activité typique sans jamais croître sans limite.
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup_logging() -> None:
    """Configure le logging racine (fichier + console, niveau INFO).

    Le chemin du fichier est surchargeable via la variable d'environnement
    LOG_FILE (jamais dans .env -- même convention que DATABASE_URL) : sert à
    isoler le fichier de test (tests/conftest.py) du vrai logs/app.log,
    sans quoi importer app.main pendant les tests écrirait dedans.
    """
    root_logger = logging.getLogger()

    if any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        return

    log_file = Path(os.environ["LOG_FILE"]) if os.environ.get("LOG_FILE") else DEFAULT_LOG_FILE
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.INFO)
