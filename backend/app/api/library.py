from collections import defaultdict
from pathlib import PurePosixPath
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, col, select, func

from ..db import get_session
from ..models import (
    Author,
    Book,
    BookAuthor,
    BookCategory,
    Category,
    RootFolder,
)
from ..services import search as search_service
from ..services.paths import display_path
from .serializers import book_card, cards_for_books, taxonomy_maps

router = APIRouter()


def folder_crumbs(folder_path: str, root_path: str) -> list[str]:
    """Display folders without WSL mount prefixes like /mnt/d."""
    display = display_path(folder_path)
    if display:
        return [p for p in PurePosixPath(display).parts if p != "/"]
    return [PurePosixPath(root_path).name]


def _is_under(path: str, folder: str) -> bool:
    path = path.rstrip("/")
    folder = folder.rstrip("/")
    return path == folder or path.startswith(folder + "/")


def _book_ids_for_category(session: Session, name: str) -> set:
    return set(
        session.exec(
            select(BookCategory.book_id)
            .join(Category, col(Category.id) == col(BookCategory.category_id))
            .where(Category.name == name)
        ).all()
    )


def _book_ids_for_author(session: Session, name: str) -> set:
    return set(
        session.exec(
            select(BookAuthor.book_id)
            .join(Author, col(Author.id) == col(BookAuthor.author_id))
            .where(Author.name == name)
        ).all()
    )


@router.get("/library")
def library(
    format: Optional[str] = None,
    folder: list[str] = Query(default=[]),
    author: Optional[str] = None,
    category: Optional[str] = None,
    sort: str = Query("title", pattern="^(title|recent)$"),
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
):
    stmt = select(Book)
    if format:
        stmt = stmt.where(Book.format == format)
    books = list(session.exec(stmt).all())

    if folder:
        books = [b for b in books if any(_is_under(b.folder_path, f) for f in folder)]
    if author:
        ids = _book_ids_for_author(session, author)
        books = [b for b in books if b.id in ids]
    if category:
        ids = _book_ids_for_category(session, category)
        books = [b for b in books if b.id in ids]

    if sort == "recent":
        books.sort(
            key=lambda b: (
                b.last_opened_at is None,
                -(b.last_opened_at.timestamp() if b.last_opened_at else 0),
                b.display_title.casefold(),
            )
        )
    else:
        books.sort(key=lambda b: b.display_title.casefold())

    total = len(books)
    books = books[offset: offset + limit]

    roots = {r.id: r.path for r in session.exec(select(RootFolder)).all()}
    authors_map, categories_map = taxonomy_maps(session, [b.id for b in books])
    sections = defaultdict(list)
    folder_root: dict[str, int] = {}
    for b in books:
        card = book_card(b, authors_map.get(b.id, []), categories_map.get(b.id, []))
        sections[b.folder_path].append(card)
        folder_root[b.folder_path] = b.root_id
    return {
        "sections": [
            {
                "folder": folder_path,
                "crumbs": folder_crumbs(
                    folder_path, roots.get(folder_root[folder_path], folder_path)
                ),
                "books": items,
            }
            for folder_path, items in sorted(sections.items())
        ],
        "total": total,
    }


@router.get("/library/filters")
def library_filters(session: Session = Depends(get_session)):
    books = session.exec(select(Book)).all()
    roots = {r.id: r.path for r in session.exec(select(RootFolder)).all()}
    formats, folder_values = set(), set()
    for b in books:
        formats.add(b.format)
        root = roots.get(b.root_id)
        if root:
            current = PurePosixPath(b.folder_path)
            root_path = PurePosixPath(root)
            while True:
                folder_values.add(str(current))
                if current == root_path or current == current.parent:
                    break
                try:
                    current.relative_to(root_path)
                except ValueError:
                    break
                current = current.parent
        else:
            folder_values.add(b.folder_path)
    folders = [
        {"value": folder, "label": display_path(folder).replace("/", " / ")}
        for folder in folder_values
    ]
    authors = [a.name for a in session.exec(select(Author).order_by(Author.name)).all()]
    categories = [
        c.name for c in session.exec(select(Category).order_by(Category.name)).all()
    ]
    return {
        "formats": sorted(formats),
        "folders": sorted(folders, key=lambda f: f["label"].casefold()),
        "authors": sorted(authors, key=str.casefold),
        "categories": sorted(categories, key=str.casefold),
    }


@router.get("/recent")
def recent(limit: int = 50, session: Session = Depends(get_session)):
    stmt = (
        select(Book)
        .where(col(Book.last_opened_at).is_not(None))
        .order_by(col(Book.last_opened_at).desc())
        .limit(limit)
    )
    return {"books": cards_for_books(session, list(session.exec(stmt).all()))}


@router.delete("/recent")
def clear_recent(session: Session = Depends(get_session)):
    books = session.exec(select(Book).where(col(Book.last_opened_at).is_not(None))).all()
    for book in books:
        book.last_opened_at = None
        session.add(book)
    session.commit()
    return {"cleared": len(books)}


@router.get("/search")
def search(q: str, session: Session = Depends(get_session)):
    if not q.strip():
        raise HTTPException(400, detail="Search query is empty.")
    books = search_service.search_books(session, q)
    return {"books": cards_for_books(session, books), "query": q.strip()}


# ---- Author / Category browse views (from first-class entities) ----

def _browse_by_links(session: Session, entity_model, link_model, link_entity_col, limit: int, offset: int):
    """Group books under each entity (Author/Category), plus an 'Unknown'
    bucket for books with none."""
    entities = session.exec(
        select(entity_model)
        .order_by(entity_model.name)
        .offset(offset)
        .limit(limit)
    ).all()
    
    total = session.exec(select(func.count(entity_model.id))).one()

    # Get only books for these specific entities to save memory
    entity_ids = [e.id for e in entities]
    book_ids = session.exec(
        select(link_model.book_id).where(link_entity_col.in_(entity_ids))
    ).all()
    
    # If offset == 0, we can also include the Unknown bucket
    unknown_book_ids = []
    if offset == 0:
        assigned_all = set(session.exec(select(link_model.book_id)).all())
        all_book_ids = set(session.exec(select(Book.id)).all())
        unknown_book_ids = list(all_book_ids - assigned_all)
        
    all_needed_book_ids = set(book_ids + unknown_book_ids)
    
    if all_needed_book_ids:
        all_books = {b.id: b for b in session.exec(select(Book).where(Book.id.in_(all_needed_book_ids))).all()}
    else:
        all_books = {}
        
    authors_map, categories_map = taxonomy_maps(session, list(all_books))

    groups = []
    assigned: set = set()
    for entity in entities:
        book_ids = session.exec(
            select(link_model.book_id).where(link_entity_col == entity.id)
        ).all()
        books = [all_books[i] for i in book_ids if i in all_books]
        assigned.update(book_ids)
        books.sort(key=lambda b: b.display_title.casefold())
        cards = [
            book_card(b, authors_map.get(b.id, []), categories_map.get(b.id, []))
            for b in books
        ]
        groups.append({"id": entity.id, "name": entity.name,
                       "count": len(cards), "books": cards})

    unknown = [b for bid, b in all_books.items() if bid not in assigned]
    if unknown:
        unknown.sort(key=lambda b: b.display_title.casefold())
        cards = [
            book_card(b, authors_map.get(b.id, []), categories_map.get(b.id, []))
            for b in unknown
        ]
        groups.append({"id": None, "name": "Unknown",
                       "count": len(cards), "books": cards})
    return {"groups": groups, "total": total + (1 if unknown else 0)}


@router.get("/browse/authors")
def browse_authors(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    return _browse_by_links(session, Author, BookAuthor, BookAuthor.author_id, limit, offset)


@router.get("/browse/categories")
def browse_categories(limit: int = 50, offset: int = 0, session: Session = Depends(get_session)):
    return _browse_by_links(session, Category, BookCategory, BookCategory.category_id, limit, offset)
