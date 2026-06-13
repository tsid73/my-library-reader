from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Author, BookAuthor
from ..services import search
from ..services.duplicates import recompute_duplicates
from .books import get_book

router = APIRouter()


class NameBody(BaseModel):
    name: str


class MergeBody(BaseModel):
    into_id: int


def _counts(session: Session) -> Dict[int, int]:
    rows = session.exec(
        select(BookAuthor.author_id, func.count()).group_by(BookAuthor.author_id)
    ).all()
    return {aid: n for aid, n in rows}


@router.get("/authors")
def list_authors(session: Session = Depends(get_session)):
    counts = _counts(session)
    authors = session.exec(select(Author).order_by(Author.name)).all()
    return [
        {"id": a.id, "name": a.name, "count": counts.get(a.id, 0)} for a in authors
    ]


@router.post("/authors", status_code=201)
def create_author(body: NameBody, session: Session = Depends(get_session)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, detail="Author name cannot be empty.")
    if session.exec(select(Author).where(Author.name == name)).first():
        raise HTTPException(409, detail=f"Author '{name}' already exists.")
    author = Author(name=name)
    session.add(author)
    session.commit()
    session.refresh(author)
    return {"id": author.id, "name": author.name, "count": 0}


@router.patch("/authors/{author_id}")
def rename_author(
    author_id: int, body: NameBody, session: Session = Depends(get_session)
):
    author = session.get(Author, author_id)
    if not author:
        raise HTTPException(404, detail="Author not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, detail="Author name cannot be empty.")
    clash = session.exec(select(Author).where(Author.name == name)).first()
    if clash and clash.id != author_id:
        raise HTTPException(409, detail=f"Author '{name}' already exists.")
    author.name = name
    session.add(author)
    session.commit()
    recompute_duplicates(session)
    search.rebuild_index(session)
    return {"id": author.id, "name": author.name}


@router.delete("/authors/{author_id}")
def delete_author(author_id: int, session: Session = Depends(get_session)):
    author = session.get(Author, author_id)
    if not author:
        raise HTTPException(404, detail="Author not found.")
    session.delete(author)  # links cascade
    session.commit()
    recompute_duplicates(session)
    search.rebuild_index(session)
    return {"ok": True}


@router.post("/authors/{author_id}/merge")
def merge_author(
    author_id: int, body: MergeBody, session: Session = Depends(get_session)
):
    """Move all of author_id's books onto into_id, then delete author_id."""
    source = session.get(Author, author_id)
    target = session.get(Author, body.into_id)
    if not source or not target:
        raise HTTPException(404, detail="Author not found.")
    if source.id == target.id:
        raise HTTPException(400, detail="Cannot merge an author into itself.")
    for link in session.exec(
        select(BookAuthor).where(BookAuthor.author_id == author_id)
    ).all():
        if not session.get(BookAuthor, (link.book_id, target.id)):
            session.add(BookAuthor(book_id=link.book_id, author_id=target.id))
    session.commit()
    # Deleting the source cascades its own links away (avoids double-delete).
    session.delete(source)
    session.commit()
    recompute_duplicates(session)
    search.rebuild_index(session)
    return {"ok": True}


@router.post("/authors/{author_id}/books/{book_id}")
def assign_book(author_id: int, book_id: int, session: Session = Depends(get_session)):
    if not session.get(Author, author_id):
        raise HTTPException(404, detail="Author not found.")
    get_book(book_id, session)
    if not session.get(BookAuthor, (book_id, author_id)):
        session.add(BookAuthor(book_id=book_id, author_id=author_id))
        session.commit()
        recompute_duplicates(session)
        search.rebuild_index(session)
    return {"ok": True}


@router.delete("/authors/{author_id}/books/{book_id}")
def unassign_book(author_id: int, book_id: int, session: Session = Depends(get_session)):
    link = session.get(BookAuthor, (book_id, author_id))
    if link:
        session.delete(link)
        session.commit()
        recompute_duplicates(session)
        search.rebuild_index(session)
    return {"ok": True}
