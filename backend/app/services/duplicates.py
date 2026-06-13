from collections import defaultdict
from typing import Dict, List

from sqlmodel import Session, col, select

from ..models import Author, Book, BookAuthor
from .titles import normalize


def _author_name_map(session: Session) -> Dict[int, str]:
    """book_id -> joined mapped author names (fallback handled by caller)."""
    names: Dict[int, list] = defaultdict(list)
    for bid, name in session.exec(
        select(BookAuthor.book_id, Author.name).join(
            Author, col(Author.id) == col(BookAuthor.author_id)
        )
    ).all():
        names[bid].append(name)
    return {bid: ", ".join(sorted(v)) for bid, v in names.items()}


def recompute_duplicates(session: Session) -> None:
    """A duplicate group = books sharing a file hash, or sharing
    (normalized title + normalized author). Group id = smallest book id
    in the group. Singletons get duplicate_group = NULL."""
    books: List[Book] = list(session.exec(select(Book)).all())
    author_names = _author_name_map(session)
    parent: Dict[int, int] = {b.id: b.id for b in books}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_hash: Dict[str, List[int]] = defaultdict(list)
    by_title_author: Dict[tuple, List[int]] = defaultdict(list)
    for b in books:
        if b.file_hash:
            by_hash[b.file_hash].append(b.id)
        title = normalize(b.display_title)
        author = normalize(author_names.get(b.id) or b.display_author)
        if title and author:
            by_title_author[(title, author)].append(b.id)

    for ids in list(by_hash.values()) + list(by_title_author.values()):
        for other in ids[1:]:
            union(ids[0], other)

    members: Dict[int, List[int]] = defaultdict(list)
    for b in books:
        members[find(b.id)].append(b.id)

    for b in books:
        root = find(b.id)
        group = root if len(members[root]) > 1 else None
        if b.duplicate_group != group:
            b.duplicate_group = group
            session.add(b)
    session.commit()
