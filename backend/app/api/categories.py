from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import BookCategory, Category
from ..services import categorize, search
from .books import get_book

router = APIRouter()


class NameBody(BaseModel):
    name: str


def _counts(session: Session) -> Dict[int, int]:
    rows = session.exec(
        select(BookCategory.category_id, func.count()).group_by(
            BookCategory.category_id
        )
    ).all()
    return {cid: n for cid, n in rows}


@router.get("/categories")
def list_categories(session: Session = Depends(get_session)):
    counts = _counts(session)
    cats = session.exec(select(Category).order_by(Category.name)).all()
    return [
        {"id": c.id, "name": c.name, "count": counts.get(c.id, 0)} for c in cats
    ]


@router.post("/categories", status_code=201)
def create_category(body: NameBody, session: Session = Depends(get_session)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, detail="Category name cannot be empty.")
    if session.exec(select(Category).where(Category.name == name)).first():
        raise HTTPException(409, detail=f"Category '{name}' already exists.")
    cat = Category(name=name)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return {"id": cat.id, "name": cat.name, "count": 0}


@router.patch("/categories/{category_id}")
def rename_category(
    category_id: int, body: NameBody, session: Session = Depends(get_session)
):
    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(404, detail="Category not found.")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, detail="Category name cannot be empty.")
    clash = session.exec(select(Category).where(Category.name == name)).first()
    if clash and clash.id != category_id:
        raise HTTPException(409, detail=f"Category '{name}' already exists.")
    cat.name = name
    session.add(cat)
    session.commit()
    search.rebuild_index(session)
    return {"id": cat.id, "name": cat.name}


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, session: Session = Depends(get_session)):
    cat = session.get(Category, category_id)
    if not cat:
        raise HTTPException(404, detail="Category not found.")
    session.delete(cat)  # links cascade
    session.commit()
    search.rebuild_index(session)
    return {"ok": True}


@router.post("/categories/{category_id}/books/{book_id}")
def assign_book(
    category_id: int, book_id: int, session: Session = Depends(get_session)
):
    if not session.get(Category, category_id):
        raise HTTPException(404, detail="Category not found.")
    get_book(book_id, session)
    if not session.get(BookCategory, (book_id, category_id)):
        session.add(BookCategory(book_id=book_id, category_id=category_id))
        session.commit()
    return {"ok": True}


@router.delete("/categories/{category_id}/books/{book_id}")
def unassign_book(
    category_id: int, book_id: int, session: Session = Depends(get_session)
):
    link = session.get(BookCategory, (book_id, category_id))
    if link:
        session.delete(link)
        session.commit()
    return {"ok": True}


@router.post("/categories/regenerate")
def regenerate(session: Session = Depends(get_session)):
    created = categorize.regenerate(session, only_if_empty=False)
    search.rebuild_index(session)
    return {"links_created": created}
