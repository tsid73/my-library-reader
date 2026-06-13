"""Backup / restore of user-created data (DB-only; original files untouched).

Exports the things the user can lose if the database is deleted: edited titles,
author and category assignments, reading progress, and bookmarks. Books are
matched on import by absolute path first, then by file hash, so a backup can be
restored after a re-index or on another machine with the same library.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Book, Bookmark, ReadingProgress
from ..services import search, taxonomy
from ..services.duplicates import recompute_duplicates
from .serializers import taxonomy_maps

router = APIRouter()

EXPORT_VERSION = 1


@router.get("/export")
def export_data(session: Session = Depends(get_session)):
    books = list(session.exec(select(Book)).all())
    authors_map, categories_map = taxonomy_maps(session, [b.id for b in books])
    progress = {p.book_id: p.position for p in session.exec(select(ReadingProgress)).all()}
    bookmarks: dict[int, list] = {}
    for bm in session.exec(select(Bookmark)).all():
        bookmarks.setdefault(bm.book_id, []).append(
            {"position": bm.position, "label": bm.label}
        )

    items = []
    for b in books:
        authors = [a.name for a in authors_map.get(b.id, [])]
        categories = [c.name for c in categories_map.get(b.id, [])]
        has_data = (
            b.edited_title or authors or categories
            or b.id in progress or b.id in bookmarks
        )
        if not has_data:
            continue
        items.append(
            {
                "abs_path": b.abs_path,
                "file_hash": b.file_hash,
                "filename": b.filename,
                "edited_title": b.edited_title,
                "authors": authors,
                "categories": categories,
                "progress": progress.get(b.id),
                "bookmarks": bookmarks.get(b.id, []),
            }
        )
    return {
        "version": EXPORT_VERSION,
        "exported_at": datetime.utcnow().isoformat(),
        "books": items,
    }


class ImportItem(BaseModel):
    abs_path: Optional[str] = None
    file_hash: Optional[str] = None
    edited_title: Optional[str] = None
    authors: List[str] = []
    categories: List[str] = []
    progress: Optional[str] = None
    bookmarks: List[dict] = []


class ImportPayload(BaseModel):
    version: int = EXPORT_VERSION
    books: List[ImportItem] = []


@router.post("/import")
def import_data(payload: ImportPayload, session: Session = Depends(get_session)):
    by_path = {b.abs_path: b for b in session.exec(select(Book)).all()}
    by_hash: dict[str, Book] = {}
    for b in by_path.values():
        by_hash.setdefault(b.file_hash, b)

    matched = 0
    skipped = 0
    for item in payload.books:
        book = (item.abs_path and by_path.get(item.abs_path)) or (
            item.file_hash and by_hash.get(item.file_hash)
        )
        if not book:
            skipped += 1
            continue
        matched += 1

        if item.edited_title is not None:
            book.edited_title = item.edited_title or None
            session.add(book)
            session.commit()

        if item.authors:
            ids = [taxonomy.get_or_create_author(session, n).id for n in item.authors if n.strip()]
            taxonomy.set_book_authors(session, book.id, ids)
        if item.categories:
            ids = [taxonomy.get_or_create_category(session, n).id for n in item.categories if n.strip()]
            taxonomy.set_book_categories(session, book.id, ids)

        if item.progress:
            prog = session.get(ReadingProgress, book.id)
            if prog:
                prog.position = item.progress
            else:
                prog = ReadingProgress(book_id=book.id, position=item.progress)
            session.add(prog)
            session.commit()

        existing_positions = {
            bm.position
            for bm in session.exec(
                select(Bookmark).where(Bookmark.book_id == book.id)
            ).all()
        }
        for bm in item.bookmarks:
            pos = bm.get("position")
            if pos and pos not in existing_positions:
                session.add(
                    Bookmark(book_id=book.id, position=pos, label=bm.get("label"))
                )
                existing_positions.add(pos)
        session.commit()

    recompute_duplicates(session)
    search.rebuild_index(session)
    return {"matched": matched, "skipped": skipped}
