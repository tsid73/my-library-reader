"""Lazy cover extraction.

Covers are no longer rendered during sync (PDF first-page rendering over a
network mount made sync very slow). Instead each book starts with
cover_state='pending' and its cover is extracted on first request via the
cover endpoint, then cached. This keeps sync fast and naturally parallelises
extraction across concurrent image requests from the grid.
"""
import os
from typing import Optional

from sqlmodel import Session

from .. import config
from ..models import Book
from . import extract


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
