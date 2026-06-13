# Architecture

A local-first ebook library and reader. A FastAPI + SQLite backend indexes
ebook files **in place** (never copying or modifying them) and a React + Vite
SPA renders the library and the readers.

```
Browser (SPA)  ──HTTP /api──▶  FastAPI  ──▶  SQLite (library.db)
   PDF.js / epub.js                 │
   readers                          ├──▶  filesystem (original book files, read-only)
                                    └──▶  data/covers (extracted JPEG covers)
```

## Stack

| Layer    | Choice                                   | Why |
|----------|------------------------------------------|-----|
| Backend  | FastAPI, SQLModel, SQLite                | Simple single-file DB; SQLModel = Pydantic + SQLAlchemy in one model |
| Parsing  | ebooklib (EPUB), pypdf + PyMuPDF (PDF), Pillow | Metadata + cover extraction |
| Frontend | React, TypeScript, Vite                  | Fast dev server, typed UI |
| Readers  | PDF.js, epub.js, custom TXT/HTML         | Mature in-browser engines |
| Search   | SQLite FTS5 (LIKE fallback)              | Ranked, Unicode-aware, no extra service |

## Repository layout

```
backend/
  main.py                 entry: init DB, migrate, seed root, rebuild search, run uvicorn (:8011)
  app/
    __init__.py           create_app(): routers + (prod) static SPA serving
    config.py             env config (LIBRARY_ROOT, LIBRARY_DATA_DIR), .env loader
    db.py                 engine (WAL + busy_timeout), schema migration, FTS5 setup
    models.py             all tables (one SQLModel each)
    api/                  roots, sync, library, books, reader, progress, bookmarks
    services/
      scanner.py          walk roots, apply include/exclude rules
      hashing.py          partial hash (size + first/last 1 MiB)
      sync.py             background sync orchestration + progress
      titles.py           conservative filename -> title/author cleanup
      extract.py          embedded metadata + cover bytes (hardened Pillow)
      covers.py           lazy cover extraction + cache
      duplicates.py       duplicate-group recompute (union-find)
      search.py           FTS5 index rebuild + query
      safe_paths.py       path-containment check for HTML assets
  tests/                  pytest (unit + integration + API)
frontend/
  src/
    api/client.ts         typed fetch wrappers (surfaces backend error detail)
    pages/                LibraryPage, RecentPage, ReaderPage, ManageEntitiesPage, BookmarksPage
    components/           BookCard, SyncPanel, MetadataModal, FoldersPanel
    readers/              PdfReader, EpubReader, TextReader, HtmlReader
    test/                 Vitest component + client tests
```

## Data model (SQLite)

- **root_folders** — indexed library roots.
- **folder_rules** — per-root include/exclude subpaths (exclude wins).
- **books** — one row per file. Absolute path (unique), folder path, format,
  size, mtime, partial hash, filename-derived `cleaned_*` and user `edited_*`
  metadata, `cover_path` + `cover_state` (pending/ok/none), `epub_locations`
  cache, `duplicate_group`, `last_opened_at`.
- **reading_progress** — one row per book (PK = book_id), position = PDF page
  number or EPUB CFI.
- **bookmarks** — many per book; position is page number or CFI.
- **sync_runs / sync_errors** — per-run counters and actionable per-file errors.
- **books_fts** — FTS5 virtual table (title/author/series/category/path),
  rebuilt after sync and metadata edits.

`book_metadata` was intentionally **merged into `books`** as `edited_*` columns
(a 1:1 side table adds joins for no benefit).

Deleting a book cascades to progress and bookmarks (FK `ON DELETE CASCADE`);
sync additionally removes the cached cover file.

## Sync algorithm (`services/sync.py`)

Runs on one background thread; the UI polls `GET /api/sync/status`.

1. Walk each available root, applying include/exclude rules; collect supported
   files (`.epub .pdf .txt .html .htm`); ignore `.mobi .azw3`.
2. Diff against the DB by absolute path:
   - **unchanged** (size + mtime match) → skip
   - **changed** → re-hash, re-extract metadata, mark cover pending
   - **new** → hash; if the hash matches a file now missing from disk → treat as
     a **rename/move** (keep progress, bookmarks, edited metadata); else insert
     with conservative filename cleanup + embedded EPUB/PDF metadata
   - **missing from disk** (and whose root *was* scanned) → delete row + cover
3. Recompute duplicate groups, rebuild the FTS index, write run summary.

**Change detection is cheap on purpose.** Full-file hashing over a network
mount (e.g. WSL `/mnt/d`) is slow, so the hash is `SHA-256(size + first 1 MiB +
last 1 MiB)` and is only computed when size/mtime changed.

**Offline roots never delete.** If a root is unavailable (unmounted drive), it
is skipped and its books are excluded from the deletion pass — a missing drive
must never purge the library.

## Covers — lazy extraction

Covers are **not** rendered during sync (PDF first-page rendering over a mount
made sync minutes-long). Each book starts `cover_state='pending'`; the cover
endpoint extracts and caches on first request, then serves the cached JPEG.
This keeps sync fast and parallelises naturally across the grid's concurrent
image requests. `has_cover` is true unless `cover_state='none'`, so the grid
always attempts the cover and falls back to a generated placeholder on 404.

## Readers

- **PDF** (PDF.js) — continuous **scroll** mode (lazy per-page canvases via
  IntersectionObserver, slots pre-sized from page-1 aspect ratio) or **paged**
  mode; the choice is remembered. Progress = page number.
- **EPUB** (epub.js) — the archive is fetched as bytes and opened (passing the
  URL would make epub.js treat the extensionless path as an unpacked folder).
  Progress/bookmarks = CFI. epub.js locations are generated once and cached in
  the DB for an instant whole-book percentage on reopen.
- **TXT / HTML** — readable views; HTML runs in a sandboxed iframe and loads
  same-folder assets only, via a path-containment-checked route.

## Security model

The app deliberately serves local files (`/books/{id}/file`, HTML assets) and
has **no authentication**. It binds to `127.0.0.1` and must not be exposed to a
network. HTML asset serving is restricted to the book's own folder
(`safe_paths.resolve_inside` rejects `..` and symlink escapes).

## Key decisions / trade-offs

- Polling over WebSockets for sync progress — simpler, fine at this scale.
- One worker thread for sync — blocking file I/O doesn't belong on the async
  loop; WAL + `busy_timeout` let readers and the writer coexist.
- Full FTS rebuild after sync/edit instead of incremental triggers — trivial
  for a < 1000-book library, far simpler to reason about.
- Conservative title cleanup — never destroy title info when unsure.
