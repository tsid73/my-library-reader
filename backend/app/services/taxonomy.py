"""First-class Category/Author helpers: get-or-create, book<->entity mapping,
and one-time seeding from existing book data. Authors and categories are
many-to-many with books (a book can have several of each)."""
from typing import List

from sqlmodel import Session, select

from ..models import Author, Book, BookAuthor, BookCategory, Category


# ---- generic get-or-create ----
def get_or_create_category(session: Session, name: str) -> Category:
    name = name.strip()
    existing = session.exec(select(Category).where(Category.name == name)).first()
    if existing:
        return existing
    cat = Category(name=name)
    session.add(cat)
    session.commit()
    session.refresh(cat)
    return cat


def get_or_create_author(session: Session, name: str) -> Author:
    name = name.strip()
    existing = session.exec(select(Author).where(Author.name == name)).first()
    if existing:
        return existing
    author = Author(name=name)
    session.add(author)
    session.commit()
    session.refresh(author)
    return author


# ---- per-book lookups ----
def categories_for_book(session: Session, book_id: int) -> List[Category]:
    rows = session.exec(
        select(Category)
        .join(BookCategory, BookCategory.category_id == Category.id)
        .where(BookCategory.book_id == book_id)
        .order_by(Category.name)
    ).all()
    return list(rows)


def authors_for_book(session: Session, book_id: int) -> List[Author]:
    rows = session.exec(
        select(Author)
        .join(BookAuthor, BookAuthor.author_id == Author.id)
        .where(BookAuthor.book_id == book_id)
        .order_by(Author.name)
    ).all()
    return list(rows)


def author_names_for_book(session: Session, book_id: int) -> str:
    return ", ".join(a.name for a in authors_for_book(session, book_id))


# ---- mapping mutations ----
def set_book_categories(session: Session, book_id: int, category_ids: List[int]) -> None:
    for link in session.exec(
        select(BookCategory).where(BookCategory.book_id == book_id)
    ).all():
        session.delete(link)
    for cid in dict.fromkeys(category_ids):
        if session.get(Category, cid):
            session.add(BookCategory(book_id=book_id, category_id=cid))
    session.commit()


def set_book_authors(session: Session, book_id: int, author_ids: List[int]) -> None:
    for link in session.exec(
        select(BookAuthor).where(BookAuthor.book_id == book_id)
    ).all():
        session.delete(link)
    for aid in dict.fromkeys(author_ids):
        if session.get(Author, aid):
            session.add(BookAuthor(book_id=book_id, author_id=aid))
    session.commit()


def link_category(session: Session, book_id: int, category_id: int) -> None:
    if not session.get(BookCategory, (book_id, category_id)):
        session.add(BookCategory(book_id=book_id, category_id=category_id))
        session.commit()


def link_author(session: Session, book_id: int, author_id: int) -> None:
    if not session.get(BookAuthor, (book_id, author_id)):
        session.add(BookAuthor(book_id=book_id, author_id=author_id))
        session.commit()


# ---- seeding ----
def seed_authors(session: Session) -> int:
    """Create Author rows + links from existing book author strings. Runs once
    (no-op if any authors already exist). Returns number of links created."""
    if session.exec(select(Author).limit(1)).first():
        return 0
    cache: dict[str, Author] = {}
    links = 0
    for book in session.exec(select(Book)).all():
        name = (book.edited_author or book.cleaned_author or "").strip()
        if not name:
            continue
        author = cache.get(name.casefold())
        if author is None:
            author = get_or_create_author(session, name)
            cache[name.casefold()] = author
        if not session.get(BookAuthor, (book.id, author.id)):
            session.add(BookAuthor(book_id=book.id, author_id=author.id))
            links += 1
    session.commit()
    return links
