"""Metadata search backed by SQLite FTS5, with a LIKE fallback when the
SQLite build lacks FTS5. The index is rebuilt after each sync and after
metadata edits (the library is small, so a full rebuild is cheap)."""
import re
from collections import defaultdict
from typing import Dict, List

from sqlalchemy import text
from sqlmodel import Session, col, or_, select

from .. import db
from ..models import Author, Book, BookAuthor, BookCategory, Category


def _author_names(session: Session) -> Dict[int, str]:
    names: Dict[int, list] = defaultdict(list)
    for bid, name in session.exec(
        select(BookAuthor.book_id, Author.name).join(
            Author, col(Author.id) == col(BookAuthor.author_id)
        )
    ).all():
        names[bid].append(name)
    return {bid: " ".join(v) for bid, v in names.items()}


def _category_names(session: Session) -> Dict[int, str]:
    names: Dict[int, list] = defaultdict(list)
    for bid, name in session.exec(
        select(BookCategory.book_id, Category.name).join(
            Category, col(Category.id) == col(BookCategory.category_id)
        )
    ).all():
        names[bid].append(name)
    return {bid: " ".join(v) for bid, v in names.items()}


def _author_names_for_book(session: Session, book_id: int) -> str:
    names = session.exec(
        select(Author.name).join(
            BookAuthor, col(Author.id) == col(BookAuthor.author_id)
        ).where(BookAuthor.book_id == book_id)
    ).all()
    return " ".join(names)


def _category_names_for_book(session: Session, book_id: int) -> str:
    names = session.exec(
        select(Category.name).join(
            BookCategory, col(Category.id) == col(BookCategory.category_id)
        ).where(BookCategory.book_id == book_id)
    ).all()
    return " ".join(names)


def rebuild_index(session: Session) -> None:
    if not db.fts5_available:
        return
    conn = session.connection()
    conn.execute(text("DELETE FROM books_fts"))
    authors = _author_names(session)
    categories = _category_names(session)
    for book in session.exec(select(Book)).all():
        conn.execute(
            text(
                "INSERT INTO books_fts(rowid, title, author, series, category, path) "
                "VALUES (:r, :t, :a, :s, :c, :p)"
            ),
            {
                "r": book.id,
                # Index both the shown title and the embedded title so a book is
                # findable by either.
                "t": " ".join(
                    filter(
                        None,
                        [book.edited_title or book.cleaned_title, book.meta_title],
                    )
                ),
                "a": authors.get(book.id) or book.cleaned_author or "",
                "s": book.edited_series or "",
                "c": categories.get(book.id, ""),
                "p": book.abs_path or "",
            },
        )
    session.commit()


def update_index_for_book(session: Session, book: Book) -> None:
    if not db.fts5_available:
        return
    conn = session.connection()
    conn.execute(text("DELETE FROM books_fts WHERE rowid = :r"), {"r": book.id})
    author_str = _author_names_for_book(session, book.id)
    category_str = _category_names_for_book(session, book.id)
    conn.execute(
        text(
            "INSERT INTO books_fts(rowid, title, author, series, category, path) "
            "VALUES (:r, :t, :a, :s, :c, :p)"
        ),
        {
            "r": book.id,
            "t": " ".join(
                filter(
                    None,
                    [book.edited_title or book.cleaned_title, book.meta_title],
                )
            ),
            "a": author_str or book.cleaned_author or "",
            "s": book.edited_series or "",
            "c": category_str,
            "p": book.abs_path or "",
        },
    )
    session.commit()


def _match_query(q: str) -> str:
    # Turn free text into a forgiving prefix AND query: harry pot -> "harry"* "pot"*
    terms = re.findall(r"\w+", q, flags=re.UNICODE)
    return " ".join(f'"{t}"*' for t in terms)


def search_books(session: Session, q: str) -> List[Book]:
    q = q.strip()
    if not q:
        return []

    if db.fts5_available:
        match = _match_query(q)
        if match:
            try:
                rows = session.connection().execute(
                    text(
                        "SELECT rowid FROM books_fts WHERE books_fts MATCH :m "
                        "ORDER BY rank"
                    ),
                    {"m": match},
                )
                ids = [r[0] for r in rows]
                if not ids:
                    return []
                books = {b.id: b for b in session.exec(
                    select(Book).where(col(Book.id).in_(ids))
                ).all()}
                return [books[i] for i in ids if i in books]  # preserve rank order
            except Exception:
                pass  # fall through to LIKE

    pattern = f"%{q}%"
    stmt = select(Book).where(
        or_(
            col(Book.cleaned_title).like(pattern),
            col(Book.edited_title).like(pattern),
            col(Book.cleaned_author).like(pattern),
            col(Book.edited_author).like(pattern),
            col(Book.edited_series).like(pattern),
            col(Book.edited_category).like(pattern),
            col(Book.abs_path).like(pattern),
        )
    )
    return sorted(session.exec(stmt).all(), key=lambda b: b.display_title.casefold())
