import logging
import os

from sqlmodel import Session, select

from app import config, create_app, db
from app.models import RootFolder

app = create_app()


def seed_default_root() -> None:
    with Session(db.engine) as session:
        if session.exec(select(RootFolder)).first():
            return
        if not config.DEFAULT_ROOT:
            print(
                "No LIBRARY_ROOT configured. Add a root folder from the app's "
                "Folders panel (or set LIBRARY_ROOT in backend/.env)."
            )
        elif os.path.isdir(config.DEFAULT_ROOT):
            session.add(RootFolder(path=config.DEFAULT_ROOT))
            session.commit()
            print(f"Preconfigured root folder: {config.DEFAULT_ROOT}")
        else:
            print(
                f"WARNING: LIBRARY_ROOT {config.DEFAULT_ROOT} was not found. "
                "Add a root folder from the app UI once it opens."
            )


def seed_taxonomy() -> None:
    """One-time, idempotent: derive first-class authors from existing author
    strings and intelligent categories from book titles/paths."""
    from app.services import categorize, taxonomy

    with Session(db.engine) as session:
        author_links = taxonomy.seed_authors(session)
        category_links = categorize.regenerate(session, only_if_empty=True)
    if author_links or category_links:
        print(
            f"Seeded taxonomy: {author_links} author links, "
            f"{category_links} category links."
        )


def backfill_titles() -> None:
    """One-time: when the meta_title column is first added, re-derive every
    book's cleaned_title from its filename so the default title is the file
    name. The old (often metadata) title was preserved into meta_title by the
    migration; drop it when it's identical to the file title."""
    if not db.titles_need_backfill:
        return
    from app.services.titles import clean_filename
    from app.models import Book
    import os

    with Session(db.engine) as session:
        books = session.exec(select(Book)).all()
        for book in books:
            file_title = clean_filename(os.path.splitext(book.filename)[0])[0]
            if book.meta_title and book.meta_title == file_title:
                book.meta_title = None
            book.cleaned_title = file_title
            session.add(book)
        session.commit()
    db.titles_need_backfill = False
    print(f"Backfilled filename titles for {len(books)} books.")


def rebuild_search_index() -> None:
    """Populate the FTS index at startup so search works before the first
    sync (e.g. after upgrading an existing database)."""
    from app.services import search

    with Session(db.engine) as session:
        search.rebuild_index(session)


def port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def configure_logging() -> None:
    # Keep tolerant PDF parsing, but suppress pypdf warning spam for malformed
    # files that are already surfaced through sync errors and fallbacks.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        import fitz  # PyMuPDF

        from app.services.extract import _quiet_pymupdf

        _quiet_pymupdf(fitz)
    except Exception:
        pass


if __name__ == "__main__":
    import sys

    import uvicorn

    from app import serving_spa

    configure_logging()
    config.ensure_dirs()
    db.init_engine()
    db.create_tables()
    backfill_titles()
    seed_default_root()
    seed_taxonomy()
    rebuild_search_index()

    if port_in_use(config.BACKEND_HOST, config.BACKEND_PORT):
        print(
            f"\n  ✗ Port {config.BACKEND_PORT} is already in use.\n"
            f"    Another instance is probably running. Stop it, or start on a\n"
            f"    different port:  BACKEND_PORT=8012 npm run dev\n"
        )
        sys.exit(1)

    if serving_spa():
        print(f"\n  ▶ Open the app:  {config.BACKEND_URL}\n")
    else:
        print(f"\n  ▶ API on {config.BACKEND_URL}")
        print(f"  ▶ Open the app:  {config.FRONTEND_URL}  (run: npm run dev)\n")
    try:
        uvicorn.run(
            app,
            host=config.BACKEND_HOST,
            port=config.BACKEND_PORT,
            access_log=False,
            lifespan="off",
        )
    except KeyboardInterrupt:
        pass
