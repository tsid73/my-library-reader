import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from .. import config
from ..db import get_session
from ..models import Book
from ..services import extract, search, taxonomy
from ..services.covers import ensure_cover
from ..services.duplicates import recompute_duplicates
from .serializers import book_detail

router = APIRouter()


class MetadataUpdate(BaseModel):
    edited_title: Optional[str] = None


class NamesUpdate(BaseModel):
    names: List[str]


def get_book(book_id: int, session: Session) -> Book:
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(404, detail=f"Book #{book_id} not found.")
    return book


def _reindex(session: Session) -> None:
    recompute_duplicates(session)
    search.rebuild_index(session)


@router.get("/books/{book_id}")
def book_details(book_id: int, session: Session = Depends(get_session)):
    return book_detail(get_book(book_id, session), session)


@router.patch("/books/{book_id}")
def update_metadata(
    book_id: int, body: MetadataUpdate, session: Session = Depends(get_session)
):
    book = get_book(book_id, session)
    data = body.model_dump(exclude_unset=True)
    if "edited_title" in data:
        value = data["edited_title"]
        book.edited_title = value.strip() if value else None
    session.add(book)
    session.commit()
    _reindex(session)
    session.refresh(book)
    return book_detail(book, session)


@router.put("/books/{book_id}/authors")
def set_authors(
    book_id: int, body: NamesUpdate, session: Session = Depends(get_session)
):
    get_book(book_id, session)
    ids = [
        taxonomy.get_or_create_author(session, n).id
        for n in body.names
        if n.strip()
    ]
    taxonomy.set_book_authors(session, book_id, ids)
    _reindex(session)
    return book_detail(get_book(book_id, session), session)


@router.put("/books/{book_id}/categories")
def set_categories(
    book_id: int, body: NamesUpdate, session: Session = Depends(get_session)
):
    get_book(book_id, session)
    ids = [
        taxonomy.get_or_create_category(session, n).id
        for n in body.names
        if n.strip()
    ]
    taxonomy.set_book_categories(session, book_id, ids)
    # Keep the FTS category column in sync so search reflects the edit (authors
    # already do this; categories were previously missed).
    search.rebuild_index(session)
    return book_detail(get_book(book_id, session), session)


@router.post("/books/{book_id}/open")
def mark_opened(book_id: int, session: Session = Depends(get_session)):
    book = get_book(book_id, session)
    book.last_opened_at = datetime.utcnow()
    session.add(book)
    session.commit()
    return {"ok": True}


class LocationsUpdate(BaseModel):
    locations: str  # JSON array of EPUB CFIs produced by epub.js


@router.get("/books/{book_id}/epub-locations")
def get_epub_locations(book_id: int, session: Session = Depends(get_session)):
    book = get_book(book_id, session)
    return {"locations": book.epub_locations}


@router.put("/books/{book_id}/epub-locations")
def save_epub_locations(
    book_id: int, body: LocationsUpdate, session: Session = Depends(get_session)
):
    book = get_book(book_id, session)
    book.epub_locations = body.locations
    session.add(book)
    session.commit()
    return {"ok": True}


@router.get("/books/{book_id}/cover")
def cover(book_id: int, session: Session = Depends(get_session)):
    book = get_book(book_id, session)
    path = ensure_cover(session, book)
    if not path:
        raise HTTPException(404, detail="This book has no cover.")
    # no-cache lets the browser revalidate (cheap 304s) so a replaced cover
    # shows immediately instead of serving a stale cached image.
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "no-cache"}
    )


@router.post("/books/{book_id}/cover")
async def upload_cover(
    book_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    book = get_book(book_id, session)
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, detail="Please upload an image file.")
    data = await file.read()
    if not data:
        raise HTTPException(400, detail="The uploaded image was empty.")
    config.ensure_dirs()
    dest = str(config.COVERS_DIR / f"{book.id}.jpg")
    try:
        extract.save_cover(data, dest)  # normalizes + resizes, bomb-safe
    except extract.ExtractError as exc:
        raise HTTPException(400, detail=f"Could not use that image: {exc}")
    book.cover_path = dest
    book.cover_state = "ok"
    session.add(book)
    session.commit()
    return {"ok": True}


@router.delete("/books/{book_id}/cover")
def reset_cover(book_id: int, session: Session = Depends(get_session)):
    """Forget the current cover and re-extract from the file on next request."""
    book = get_book(book_id, session)
    if book.cover_path and os.path.isfile(book.cover_path):
        try:
            os.remove(book.cover_path)
        except OSError:
            pass
    book.cover_path = None
    book.cover_state = "none" if book.format in ("txt", "html") else "pending"
    session.add(book)
    session.commit()
    return {"ok": True}
