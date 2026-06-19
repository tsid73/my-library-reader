from typing import Dict, List, Optional

from sqlmodel import Session, col, select

from ..models import Author, Book, BookAuthor, BookCategory, Category


def _entity(e) -> dict:
    return {"id": e.id, "name": e.name}


def taxonomy_maps(session: Session, book_ids: List[int]):
    """Batch-load authors and categories for many books in two queries each,
    returning {book_id: [Author]} and {book_id: [Category]}."""
    authors: Dict[int, List[Author]] = {}
    categories: Dict[int, List[Category]] = {}
    if not book_ids:
        return authors, categories
    for bid, author in session.exec(
        select(BookAuthor.book_id, Author)
        .join(Author, col(Author.id) == col(BookAuthor.author_id))
        .where(col(BookAuthor.book_id).in_(book_ids))
    ).all():
        authors.setdefault(bid, []).append(author)
    for bid, cat in session.exec(
        select(BookCategory.book_id, Category)
        .join(Category, col(Category.id) == col(BookCategory.category_id))
        .where(col(BookCategory.book_id).in_(book_ids))
    ).all():
        categories.setdefault(bid, []).append(cat)
    return authors, categories


def book_card(
    book: Book,
    authors: Optional[List[Author]] = None,
    categories: Optional[List[Category]] = None,
) -> dict:
    author_list = sorted(authors or [], key=lambda a: a.name.casefold())
    category_list = sorted(categories or [], key=lambda c: c.name.casefold())
    return {
        "id": book.id,
        "title": book.display_title,
        # Joined first-class author names; fall back to the legacy string only
        # when this book has no mapped authors yet.
        "author": ", ".join(a.name for a in author_list) or book.display_author,
        "authors": [_entity(a) for a in author_list],
        "categories": [_entity(c) for c in category_list],
        "format": book.format,
        "folder_path": book.folder_path,
        "filename": book.filename,
        "has_cover": book.cover_state != "none",
        "is_duplicate": book.duplicate_group is not None,
        "last_opened_at": book.last_opened_at.isoformat()
        if book.last_opened_at
        else None,
    }


def book_card_with_session(book: Book, session: Session) -> dict:
    """Convenience for single-book responses."""
    a, c = taxonomy_maps(session, [book.id])
    return book_card(book, a.get(book.id, []), c.get(book.id, []))


def cards_for_books(session: Session, books: List[Book]) -> List[dict]:
    """Build cards for a list of books with batched taxonomy lookups."""
    a, c = taxonomy_maps(session, [b.id for b in books])
    return [book_card(b, a.get(b.id, []), c.get(b.id, [])) for b in books]


def book_detail(book: Book, session: Session) -> dict:
    data = book_card_with_session(book, session)
    data.update(
        {
            "abs_path": book.abs_path,
            "size": book.size,
            "cleaned_title": book.cleaned_title,
            "meta_title": book.meta_title,
            "cleaned_author": book.cleaned_author,
            "edited_title": book.edited_title,
            "edited_author": book.edited_author,
            "edited_category": book.edited_category,
        }
    )
    return data
