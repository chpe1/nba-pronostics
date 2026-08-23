# Moteur de Pronostics NBA

Application de pronostics NBA basée sur un algorithme mathématique sur-mesure : confrontation de la "Note Finale" de deux équipes (% de victoires, PER des absents, malus calendrier, etc.). Usage personnel, MVP en local pour l'instant — voir [`cahier-des-charges-moteur-pronostics-nba.md`](cahier-des-charges-moteur-pronostics-nba.md) pour les spécifications complètes.

## Stack technique

- **Backend** : Python, [FastAPI](https://fastapi.tiangolo.com/), SQLAlchemy (ORM), Alembic (migrations), SQLite.
- **Frontend** : Vue.js (Vite), Vue Router, Pinia. *(à venir — Étape 5)*
- **Automatisation** : APScheduler pour les tâches planifiées.
- **Parsing** : `pandas` (CSV Basketball-Reference), `pdfplumber` (rapports de blessures PDF).
- **Tests** : `pytest`.

## État d'avancement

Roadmap complète en 7 étapes détaillée dans [`etapes-roles-projet-nba.md`](etapes-roles-projet-nba.md).

- ✅ **Étape 1 — Architecture et modélisation de la base de données** : modèles Team, Player, Game, Settings + migrations Alembic.
- ✅ **Étape 2 — Routines d'extraction de données** : import CSV manuel (stats Basketball-Reference) via back-office, parsing automatique des rapports de blessures NBA (PDF) via `pdfplumber` + APScheduler.
- ⬜ Étape 3 — Le moteur de pronostics (l'algorithme)
- ⬜ Étape 4 — Back-office et API backend
- ⬜ Étape 5 — Frontend mobile-first (Vue.js)
- ⬜ Étape 6 — Test, calibrage et validation
- ⬜ Étape 7 — Déploiement en production

## Installation

Prérequis : Python 3.11+.

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

## Base de données

Les migrations Alembic créent la base SQLite locale (`nba_pronostics.db`, non versionnée) :

```bash
alembic upgrade head
```

## Lancer l'API

```bash
uvicorn app.main:app --reload
```

Documentation interactive (Swagger) : http://127.0.0.1:8000/docs

## Tests

```bash
pytest
```

## Notes

- Basketball-Reference ne permet pas le scraping automatique : les statistiques (CSV) doivent être téléchargées manuellement puis importées via l'interface d'upload du back-office (`POST /api/imports/stats`).
- Les rapports de blessures NBA (PDF) sont récupérés et parsés automatiquement (routine planifiée, désactivée par défaut — voir `ENABLE_INJURY_SCHEDULER` dans `app/main.py`).
