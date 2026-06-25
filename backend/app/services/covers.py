"""Lazy cover extraction.

Covers are no longer rendered during sync (PDF first-page rendering over a
network mount made sync very slow). Instead each book starts with
cover_state='pending' and its cover is extracted on first request via the
cover endpoint, then cached. This keeps sync fast and naturally parallelises
extraction across concurrent image requests from the grid.
"""
import os
from typing import Optional

from sqlmodel import Session, select
import concurrent.futures
import threading

from .. import config
from ..models import Book
from . import extract

_prefetch_thread = None

def _prefetch_worker(book_id: int, abs_path: str, format: str) -> Optional[str]:
    config.ensure_dirs()
    dest = str(config.COVERS_DIR / f"{book_id}.jpg")
    try:
        if format == "epub":
            ex = extract.extract_epub(abs_path)
            data = ex.cover_bytes
        elif format == "pdf":
            data = extract.render_pdf_cover(abs_path)
        else:
            return None
        if not data:
            return None
        extract.save_cover(data, dest)
        return dest
    except extract.ExtractError:
        return None

def _run_prefetch(engine):
    with Session(engine) as session:
        books = session.exec(select(Book).where(Book.cover_state == "pending")).all()
        books_to_process = [b for b in books if b.format in ("pdf", "epub")]
    
    if not books_to_process:
        return

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(_prefetch_worker, b.id, b.abs_path, b.format): b.id
            for b in books_to_process
        }
        for future in concurrent.futures.as_completed(futures):
            book_id = futures[future]
            try:
                path = future.result()
                with Session(engine) as session:
                    b = session.get(Book, book_id)
                    if b:
                        b.cover_path = path
                        b.cover_state = "ok" if path else "none"
                        session.add(b)
                        session.commit()
            except Exception:
                with Session(engine) as session:
                    b = session.get(Book, book_id)
                    if b:
                        b.cover_state = "none"
                        session.add(b)
                        session.commit()

def start_prefetch_covers(engine):
    global _prefetch_thread
    if _prefetch_thread and _prefetch_thread.is_alive():
        return
    _prefetch_thread = threading.Thread(target=_run_prefetch, args=(engine,), daemon=True)
    _prefetch_thread.start()


def _extract_and_save(book: Book) -> Optional[str]:
    config.ensure_dirs()
    dest = str(config.COVERS_DIR / f"{book.id}.jpg")
    try:
        if book.format == "epub":
            ex = extract.extract_epub(book.abs_path)
            data = ex.cover_bytes
        elif book.format == "pdf":
            data = extract.render_pdf_cover(book.abs_path)
        else:
            return None
        if not data:
            return None
        extract.save_cover(data, dest)
        return dest
    except extract.ExtractError:
        return None


def ensure_cover(session: Session, book: Book) -> Optional[str]:
    """Return a cached cover path, extracting it on first access. Idempotent
    and safe to call concurrently (last write wins)."""
    if (
        book.cover_state == "ok"
        and book.cover_path
        and os.path.isfile(book.cover_path)
    ):
        return book.cover_path
    if book.cover_state == "none":
        return None

    path = _extract_and_save(book)
    book.cover_path = path
    book.cover_state = "ok" if path else "none"
    session.add(book)
    session.commit()
    return path
