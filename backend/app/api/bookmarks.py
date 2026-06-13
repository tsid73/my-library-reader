from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Book, Bookmark
from .serializers import book_card_with_session
from .books import get_book

router = APIRouter()


class BookmarkCreate(BaseModel):
    position: str
    label: Optional[str] = None


def _payload(b: Bookmark) -> dict:
    return {
        "id": b.id,
        "book_id": b.book_id,
        "position": b.position,
        "label": b.label,
        "created_at": b.created_at.isoformat(),
    }


@router.get("/bookmarks")
def bookmarked_books(session: Session = Depends(get_session)):
    bookmarks = session.exec(select(Bookmark).order_by(Bookmark.created_at.desc())).all()
    grouped: dict[int, list[Bookmark]] = {}
    for bookmark in bookmarks:
        grouped.setdefault(bookmark.book_id, []).append(bookmark)

    items = []
    for book_id, marks in grouped.items():
        book = session.get(Book, book_id)
        if not book:
            continue
        items.append(
            {
                "book": book_card_with_session(book, session),
                "bookmark_count": len(marks),
                "latest_bookmark": _payload(marks[0]),
            }
        )
    return {"items": items}


@router.get("/books/{book_id}/bookmarks")
def list_bookmarks(book_id: int, session: Session = Depends(get_session)):
    get_book(book_id, session)
    bookmarks = session.exec(
        select(Bookmark).where(Bookmark.book_id == book_id).order_by(Bookmark.id)
    ).all()
    return [_payload(b) for b in bookmarks]


@router.post("/books/{book_id}/bookmarks", status_code=201)
def add_bookmark(
    book_id: int, body: BookmarkCreate, session: Session = Depends(get_session)
):
    get_book(book_id, session)
    bookmark = Bookmark(
        book_id=book_id, position=body.position, label=body.label
    )
    session.add(bookmark)
    session.commit()
    session.refresh(bookmark)
    return _payload(bookmark)


@router.delete("/bookmarks/{bookmark_id}")
def delete_bookmark(bookmark_id: int, session: Session = Depends(get_session)):
    bookmark = session.get(Bookmark, bookmark_id)
    if not bookmark:
        raise HTTPException(404, detail=f"Bookmark #{bookmark_id} not found.")
    session.delete(bookmark)
    session.commit()
    return {"ok": True}
