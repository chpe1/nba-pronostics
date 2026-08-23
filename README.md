# Moteur de Pronostics NBA

> Ce projet a été codé à 100 % avec [Claude Code](https://claude.com/claude-code).

Application de pronostics NBA basée sur un algorithme mathématique sur-mesure : confrontation de la "Note Finale" de deux équipes (% de victoires, PER des absents, malus calendrier, etc.). Usage personnel, MVP en local pour l'instant.

## Stack technique

- **Backend** : Python, [FastAPI](https://fastapi.tiangolo.com/), SQLAlchemy (ORM), Alembic (migrations), SQLite.
- **Frontend** : Vue.js (Vite), Vue Router, Pinia, Tailwind CSS.
- **Automatisation** : APScheduler pour les tâches planifiées.
- **Parsing** : `pandas` (CSV Basketball-Reference), `pdfplumber` (rapports de blessures PDF).
- **Authentification** : admin unique (bcrypt + JWT).
- **Tests** : `pytest` (backend), `vitest` (frontend).

## État d'avancement

- ✅ Architecture et modélisation de la base de données (Team, Player, Game, Settings + migrations Alembic).
- ✅ Import CSV manuel (stats Basketball-Reference) via back-office, parsing automatique des rapports de blessures NBA (PDF).
- ✅ Moteur de pronostics (calcul de la Note Finale, du vainqueur, de l'écart et de l'indice de fiabilité).
- ✅ Back-office et API : authentification admin, réglages de l'algorithme, déclenchement des pronostics.
- ✅ Frontend mobile-first (Dashboard, back-office Imports/Réglages).
- ⬜ Test, calibrage et validation
- ⬜ Déploiement en production

## Installation — Backend

Prérequis : Python 3.11+.

```bash
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Copier `.env.example` en `.env` et renseigner les valeurs (voir les commentaires du fichier, notamment pour générer `ADMIN_PASSWORD_HASH` via `python scripts/generate_admin_hash.py` et `JWT_SECRET_KEY`).

### Base de données

```bash
alembic upgrade head
```

### Lancer l'API

```bash
uvicorn app.main:app --reload
```

Documentation interactive (Swagger) : http://127.0.0.1:8000/docs

### Tests

```bash
pytest
```

## Installation — Frontend

```bash
cd frontend
npm install
npm run dev
```

Copier `frontend/.env.example` en `frontend/.env.local` si l'API ne tourne pas sur `http://localhost:8000`.

```bash
npm run test    # vitest
```

## Notes

- Basketball-Reference ne permet pas le scraping automatique : les statistiques (CSV) doivent être téléchargées manuellement puis importées via l'interface d'upload du back-office (`POST /api/imports/stats`).
- Les rapports de blessures NBA (PDF) sont récupérés et parsés automatiquement (routine planifiée, désactivée par défaut — voir `ENABLE_INJURY_SCHEDULER` dans `.env`).
- Le token d'authentification admin est conservé en mémoire côté frontend (pas de persistance) : la session est perdue au rechargement de page.
