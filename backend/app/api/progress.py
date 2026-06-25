from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Bookmark, ReadingProgress
from .books import get_book

router = APIRouter()


class ProgressUpdate(BaseModel):
    position: str


@router.get("/books/{book_id}/progress")
def get_progress(book_id: int, session: Session = Depends(get_session)):
    get_book(book_id, session)
    progress = session.get(ReadingProgress, book_id)
    if not progress:
        return {"position": None, "updated_at": None}
    return {
        "position": progress.position,
        "updated_at": progress.updated_at.isoformat(),
    }


@router.put("/books/{book_id}/progress")
def save_progress(
    book_id: int, body: ProgressUpdate, session: Session = Depends(get_session)
):
    get_book(book_id, session)
    progress = session.get(ReadingProgress, book_id)
    if progress:
        progress.position = body.position
        progress.updated_at = datetime.now(timezone.utc)
    else:
        progress = ReadingProgress(book_id=book_id, position=body.position)
    session.add(progress)
    session.commit()
    return {"ok": True}


@router.delete("/books/{book_id}/reading-state")
def clear_reading_state(book_id: int, session: Session = Depends(get_session)):
    get_book(book_id, session)
    removed = 0
    progress = session.get(ReadingProgress, book_id)
    if progress:
        session.delete(progress)
        removed += 1
    bookmarks = session.exec(
        select(Bookmark).where(Bookmark.book_id == book_id)
    ).all()
    for bookmark in bookmarks:
        session.delete(bookmark)
    session.commit()
    return {"cleared_progress": progress is not None, "cleared_bookmarks": len(bookmarks)}
