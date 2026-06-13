# Contributing

## Setup

```bash
npm run setup     # installs backend (pip) + frontend (npm) deps
cp backend/.env.example backend/.env   # optional: set LIBRARY_ROOT
```

## Running

```bash
npm run dev       # backend + Vite together (one command, hot reload)
# or individually:
npm run dev:api   # backend only, :8011
npm run dev:web   # Vite only, :5173 (proxies /api to :8011)
# single-server:
npm start         # build frontend, serve whole app from :8011
```

The launcher is a thin root `package.json` using `concurrently`; the backend
serves the built SPA only when `MLR_SERVE_SPA=1` (set by `npm start`).

## Tests — run before sharing changes

```bash
cd backend  && python3 -m pytest      # backend unit + integration + API
cd frontend && npm run typecheck      # tsc --noEmit
cd frontend && npm test               # Vitest
cd frontend && npm run build          # production build
```

## Conventions

- **Never modify original book files.** The app indexes in place; sync must
  stay read-only toward the library.
- Keep error messages specific and actionable — no generic "an error occurred".
  Backend errors return `{ "detail": "..." }`; the frontend surfaces `detail`.
- New schema columns: add to `models.py` and to `_ADDED_COLUMNS` in `db.py` so
  existing databases migrate in place.
- After anything that changes searchable metadata, call
  `search.rebuild_index(session)` (and `recompute_duplicates` if titles/authors
  changed) — see `api/books.py` for the pattern.
- Match the surrounding code style; prefer the existing service/router split.

## Project docs
- Architecture & data model: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
