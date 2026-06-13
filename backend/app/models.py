from datetime import datetime
from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, SQLModel


def _fk(column: str, **kwargs):
    return Column(Integer, ForeignKey(column, ondelete="CASCADE"), **kwargs)


class RootFolder(SQLModel, table=True):
    __tablename__ = "root_folders"

    id: Optional[int] = Field(default=None, primary_key=True)
    path: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FolderRule(SQLModel, table=True):
    __tablename__ = "folder_rules"

    id: Optional[int] = Field(default=None, primary_key=True)
    root_id: int = Field(sa_column=_fk("root_folders.id", nullable=False, index=True))
    kind: str  # "include" | "exclude"
    subpath: str  # relative to the root folder


class Book(SQLModel, table=True):
    __tablename__ = "books"

    id: Optional[int] = Field(default=None, primary_key=True)
    root_id: int = Field(sa_column=_fk("root_folders.id", nullable=False, index=True))
    abs_path: str = Field(unique=True, index=True)
    folder_path: str = Field(index=True)
    filename: str
    format: str  # epub | pdf | txt | html
    size: int
    mtime: float
    file_hash: str = Field(index=True)
    cleaned_title: str
    cleaned_author: Optional[str] = None
    edited_title: Optional[str] = None
    edited_author: Optional[str] = None
    edited_series: Optional[str] = None
    edited_category: Optional[str] = None
    cover_path: Optional[str] = None
    # Lazy cover extraction state: "pending" (not tried), "ok", or "none".
    cover_state: str = Field(default="pending", index=True)
    # Cached epub.js locations JSON so reopening is instant (EPUB only).
    epub_locations: Optional[str] = None
    duplicate_group: Optional[int] = Field(default=None, index=True)
    last_opened_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def display_title(self) -> str:
        return self.edited_title or self.cleaned_title

    @property
    def display_author(self) -> Optional[str]:
        return self.edited_author or self.cleaned_author


class Category(SQLModel, table=True):
    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Author(SQLModel, table=True):
    __tablename__ = "authors"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BookCategory(SQLModel, table=True):
    __tablename__ = "book_categories"

    book_id: int = Field(sa_column=_fk("books.id", primary_key=True))
    category_id: int = Field(sa_column=_fk("categories.id", primary_key=True))


class BookAuthor(SQLModel, table=True):
    __tablename__ = "book_authors"

    book_id: int = Field(sa_column=_fk("books.id", primary_key=True))
    author_id: int = Field(sa_column=_fk("authors.id", primary_key=True))


class ReadingProgress(SQLModel, table=True):
    __tablename__ = "reading_progress"

    book_id: int = Field(sa_column=_fk("books.id", primary_key=True))
    position: str  # PDF: page number as string; EPUB: CFI
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Bookmark(SQLModel, table=True):
    __tablename__ = "bookmarks"

    id: Optional[int] = Field(default=None, primary_key=True)
    book_id: int = Field(sa_column=_fk("books.id", nullable=False, index=True))
    position: str
    label: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SyncRun(SQLModel, table=True):
    __tablename__ = "sync_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    found: int = 0
    indexed: int = 0
    skipped: int = 0
    deleted: int = 0
    failed: int = 0


class SyncError(SQLModel, table=True):
    __tablename__ = "sync_errors"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(sa_column=_fk("sync_runs.id", nullable=False, index=True))
    file_path: str
    message: str
