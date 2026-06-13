import logging
import os
import time

import pytest
from sqlmodel import Session, select

from app.models import Book, Bookmark, ReadingProgress, RootFolder, SyncError
from app.services.extract import ExtractError, extract_pdf_metadata
from app.services.sync import SyncManager
from tests.conftest import make_epub, make_pdf


def run_sync(engine):
    manager = SyncManager()
    manager.start(engine)
    manager.wait()
    return manager.progress


def setup_library(tmp_path):
    lib = tmp_path / "library"
    (lib / "Novels").mkdir(parents=True)
    (lib / "Study" / "Tech").mkdir(parents=True)
    make_epub(lib / "Novels" / "Brandon Sanderson - Elantris.epub",
              title="Elantris", author="Brandon Sanderson", cover=True)
    make_pdf(lib / "Study" / "Tech" / "algorithms.pdf", title="Algorithms")
    (lib / "Novels" / "notes.txt").write_text("plain text book")
    (lib / "Study" / "page.html").write_text("<html><body>hi</body></html>")
    (lib / "Novels" / "ignored.mobi").write_bytes(b"mobi data")
    return lib


def test_full_sync_cycle(engine, tmp_path):
    lib = setup_library(tmp_path)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()

    p = run_sync(engine)
    assert p.fatal_error is None
    assert p.found == 4  # mobi ignored
    assert p.indexed == 4
    assert p.failed == 0

    with Session(engine) as s:
        books = {b.filename: b for b in s.exec(select(Book)).all()}
        assert len(books) == 4
        epub = books["Brandon Sanderson - Elantris.epub"]
        # Embedded metadata wins over filename parse
        assert epub.cleaned_title == "Elantris"
        assert epub.cleaned_author == "Brandon Sanderson"
        # Covers are extracted lazily now, so sync only marks them pending.
        assert epub.cover_state == "pending"
        assert epub.cover_path is None
        pdf = books["algorithms.pdf"]
        assert pdf.cleaned_title == "Algorithms"  # embedded PDF title
        assert pdf.cover_state == "pending"
        txt = books["notes.txt"]
        assert txt.cover_state == "none"  # no cover possible

    # Second sync: everything unchanged
    p2 = run_sync(engine)
    assert p2.skipped == 4
    assert p2.indexed == 0
    assert p2.deleted == 0


def test_delete_removes_everything(engine, tmp_path):
    lib = setup_library(tmp_path)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)

    with Session(engine) as s:
        book = s.exec(
            select(Book).where(Book.filename == "notes.txt")
        ).one()
        book_id = book.id
        s.add(ReadingProgress(book_id=book_id, position="3"))
        s.add(Bookmark(book_id=book_id, position="5"))
        s.commit()

    os.remove(lib / "Novels" / "notes.txt")
    p = run_sync(engine)
    assert p.deleted == 1

    with Session(engine) as s:
        assert s.get(Book, book_id) is None
        assert s.get(ReadingProgress, book_id) is None
        assert not s.exec(
            select(Bookmark).where(Bookmark.book_id == book_id)
        ).all()


def test_rename_keeps_progress(engine, tmp_path):
    lib = setup_library(tmp_path)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)

    with Session(engine) as s:
        book = s.exec(
            select(Book).where(Book.filename == "algorithms.pdf")
        ).one()
        book_id = book.id
        book.edited_title = "My Algorithms Book"
        s.add(book)
        s.add(ReadingProgress(book_id=book_id, position="42"))
        s.commit()

    os.rename(
        lib / "Study" / "Tech" / "algorithms.pdf",
        lib / "Study" / "Tech" / "algorithms-renamed.pdf",
    )
    p = run_sync(engine)
    assert p.deleted == 0

    with Session(engine) as s:
        book = s.get(Book, book_id)
        assert book is not None
        assert book.filename == "algorithms-renamed.pdf"
        assert book.edited_title == "My Algorithms Book"
        progress = s.get(ReadingProgress, book_id)
        assert progress.position == "42"


def test_changed_file_reindexed(engine, tmp_path):
    lib = setup_library(tmp_path)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)

    target = lib / "Novels" / "notes.txt"
    time.sleep(0.01)
    target.write_text("completely new content that is longer")
    os.utime(target, (time.time() + 5, time.time() + 5))
    p = run_sync(engine)
    assert p.indexed == 1
    assert p.skipped == 3


def test_corrupt_epub_indexed_with_error(engine, tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "broken.epub").write_bytes(b"this is not a zip file")
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()

    p = run_sync(engine)
    assert p.fatal_error is None
    assert p.indexed == 1  # indexed from filename despite corruption
    assert len(p.errors) == 1
    assert "broken.epub" in p.errors[0]["file_path"]
    # Error message is specific, not generic
    assert "EPUB" in p.errors[0]["message"]

    with Session(engine) as s:
        assert s.exec(select(SyncError)).one().run_id == p.run_id


def test_corrupt_pdf_metadata_is_quiet_and_reported(engine, tmp_path, caplog):
    from main import configure_logging

    bad_pdf = tmp_path / "broken.pdf"
    bad_pdf.write_bytes(b"not a pdf")

    configure_logging()
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ExtractError):
            extract_pdf_metadata(str(bad_pdf))

    assert not any(r.name.startswith("pypdf") for r in caplog.records)

    lib = tmp_path / "library"
    lib.mkdir()
    os.rename(bad_pdf, lib / "broken.pdf")
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()

    p = run_sync(engine)
    assert p.fatal_error is None
    assert p.indexed == 1
    assert len(p.errors) == 1
    assert "broken.pdf" in p.errors[0]["file_path"]
    assert "PDF" in p.errors[0]["message"]


def test_exclude_rule_wins(engine, tmp_path):
    lib = setup_library(tmp_path)
    with Session(engine) as s:
        root = RootFolder(path=str(lib))
        s.add(root)
        s.commit()
        s.refresh(root)
        from app.models import FolderRule

        s.add(FolderRule(root_id=root.id, kind="include", subpath="Study"))
        s.add(FolderRule(root_id=root.id, kind="exclude", subpath="Study/Tech"))
        s.commit()

    p = run_sync(engine)
    with Session(engine) as s:
        books = [b.filename for b in s.exec(select(Book)).all()]
    assert books == ["page.html"]  # Novels not included, Study/Tech excluded


def test_missing_root_reports_error(engine, tmp_path):
    with Session(engine) as s:
        s.add(RootFolder(path=str(tmp_path / "does-not-exist")))
        s.commit()
    p = run_sync(engine)
    assert p.fatal_error is None
    assert len(p.errors) == 1
    assert "not found" in p.errors[0]["message"]


def test_offline_root_does_not_delete_books(engine, tmp_path):
    """If a previously-indexed root becomes unavailable, its books must NOT
    be purged (e.g. an unmounted drive)."""
    lib = setup_library(tmp_path)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)
    with Session(engine) as s:
        before = len(s.exec(select(Book)).all())
        assert before == 4

    # Make the root unavailable by renaming it on disk.
    os.rename(lib, tmp_path / "library_offline")
    p = run_sync(engine)
    assert p.deleted == 0
    assert any("skipped" in e["message"] for e in p.errors)
    with Session(engine) as s:
        assert len(s.exec(select(Book)).all()) == before  # nothing removed


def test_lazy_cover_extraction(engine, tmp_path):
    from app.services.covers import ensure_cover

    lib = setup_library(tmp_path)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)
    with Session(engine) as s:
        epub = s.exec(
            select(Book).where(Book.format == "epub")
        ).one()
        path = ensure_cover(s, epub)
        assert path and os.path.isfile(path)
        assert epub.cover_state == "ok"
        # txt has no cover
        txt = s.exec(select(Book).where(Book.format == "txt")).one()
        assert ensure_cover(s, txt) is None
        assert txt.cover_state == "none"


def test_duplicates_by_hash_and_title(engine, tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "book one.txt").write_text("identical content")
    (lib / "book one copy.txt").write_text("identical content")
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)
    with Session(engine) as s:
        books = s.exec(select(Book)).all()
        groups = {b.duplicate_group for b in books}
        assert len(groups) == 1 and None not in groups
