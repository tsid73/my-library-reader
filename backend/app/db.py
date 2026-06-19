from typing import Iterator

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from . import config

engine = None

# Whether the SQLite build supports FTS5 (detected at table-creation time).
fts5_available = False


def make_engine(db_path=None):
    path = db_path if db_path is not None else config.DB_PATH
    eng = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(eng, "connect")
    def _on_connect(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets readers and the background sync writer coexist without
        # "database is locked"; busy_timeout waits instead of erroring.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return eng


def init_engine(db_path=None):
    global engine
    engine = make_engine(db_path)
    return engine


# Columns added after the first release. SQLite ADD COLUMN is cheap and only
# runs when the column is missing, so existing databases upgrade in place.
_ADDED_COLUMNS = {
    "cover_state": "ALTER TABLE books ADD COLUMN cover_state TEXT DEFAULT 'pending'",
    "epub_locations": "ALTER TABLE books ADD COLUMN epub_locations TEXT",
    "meta_title": "ALTER TABLE books ADD COLUMN meta_title TEXT",
}

# Set when the meta_title column was just created, so the app knows to re-derive
# filename titles for pre-existing rows (see main.backfill_titles).
titles_need_backfill = False


def _migrate(conn) -> None:
    global titles_need_backfill
    existing = {row[1] for row in conn.execute(text("PRAGMA table_info(books)"))}
    for column, ddl in _ADDED_COLUMNS.items():
        if column not in existing:
            conn.execute(text(ddl))
    if "meta_title" not in existing:
        # Preserve the currently-shown (often metadata) title as the metadata
        # choice; main.backfill_titles() then re-derives cleaned_title from the
        # filename so the default becomes the file name.
        conn.execute(text("UPDATE books SET meta_title = cleaned_title"))
        titles_need_backfill = True
    # Backfill cover_state for rows that predate the column so already-extracted
    # covers aren't needlessly re-rendered.
    if "cover_state" not in existing:
        conn.execute(
            text("UPDATE books SET cover_state='ok' WHERE cover_path IS NOT NULL")
        )
        conn.execute(
            text(
                "UPDATE books SET cover_state='none' "
                "WHERE cover_path IS NULL AND format IN ('txt','html')"
            )
        )
        conn.execute(
            text(
                "UPDATE books SET cover_state='pending' "
                "WHERE cover_path IS NULL AND format IN ('epub','pdf')"
            )
        )


def _setup_fts(conn) -> bool:
    """Create an FTS5 search index over book metadata. Returns False if the
    SQLite build lacks FTS5 (search then falls back to LIKE)."""
    try:
        # Standalone FTS table (stores its own copy of the text) keyed by
        # rowid = book.id, so it is trivially rebuilt after sync / edits.
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5("
                "title, author, series, category, path, "
                "tokenize='unicode61')"
            )
        )
        return True
    except Exception:
        return False


def create_tables(eng=None) -> None:
    global fts5_available
    eng = eng or engine
    SQLModel.metadata.create_all(eng)
    with eng.begin() as conn:
        _migrate(conn)
        fts5_available = _setup_fts(conn)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
