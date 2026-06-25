import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlmodel import Session, select

from .. import config
from ..models import Book, FolderRule, RootFolder, SyncError, SyncRun
from . import extract, search
from .duplicates import recompute_duplicates
from .hashing import partial_hash
from .scanner import ScannedFile, scan_root
from .titles import clean_filename


class SyncAlreadyRunning(Exception):
    pass


class SyncStopped(Exception):
    pass


@dataclass
class SyncProgress:
    running: bool = False
    run_id: Optional[int] = None
    current_folder: str = ""
    current_file: str = ""
    found: int = 0
    indexed: int = 0
    skipped: int = 0
    deleted: int = 0
    failed: int = 0
    errors: List[dict] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    fatal_error: Optional[str] = None
    stopping: bool = False
    stopped: bool = False

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "run_id": self.run_id,
            "current_folder": self.current_folder,
            "current_file": self.current_file,
            "found": self.found,
            "indexed": self.indexed,
            "skipped": self.skipped,
            "deleted": self.deleted,
            "failed": self.failed,
            "errors": list(self.errors),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "fatal_error": self.fatal_error,
            "stopping": self.stopping,
            "stopped": self.stopped,
        }


class SyncManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.progress = SyncProgress()

    def start(self, engine, only_root_id: Optional[int] = None) -> int:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise SyncAlreadyRunning()
            with Session(engine) as session:
                run = SyncRun()
                session.add(run)
                session.commit()
                session.refresh(run)
                run_id = run.id
            self._stop_event.clear()
            self.progress = SyncProgress(
                running=True,
                run_id=run_id,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._thread = threading.Thread(
                target=self._run, args=(engine, run_id, only_root_id), daemon=True
            )
            self._thread.start()
            return run_id

    def stop(self) -> bool:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return False
        self.progress.stopping = True
        self._stop_event.set()
        return True

    def wait(self) -> None:
        """Block until the current sync finishes (used by tests)."""
        thread = self._thread
        if thread is not None:
            thread.join()

    def get_progress_dict(self) -> dict:
        with self._lock:
            return self.progress.to_dict()

    # ----- worker -----

    def _record_error(self, session: Session, run_id: int, path: str, message: str):
        session.add(SyncError(run_id=run_id, file_path=path, message=message))
        session.commit()
        with self._lock:
            self.progress.errors.append({"file_path": path, "message": message})

    def _run(self, engine, run_id: int, only_root_id: Optional[int] = None) -> None:
        p = self.progress
        try:
            with Session(engine) as session:
                self._sync(session, run_id, only_root_id)
        except SyncStopped:
            p.stopped = True
            p.stopping = False
        except Exception as exc:  # never let the worker die silently
            p.fatal_error = f"Sync aborted: {exc}"
            try:
                with Session(engine) as session:
                    self._record_error(session, run_id, "", p.fatal_error)
            except Exception:
                pass
        finally:
            p.running = False
            p.current_folder = ""
            p.current_file = ""
            p.finished_at = datetime.now(timezone.utc).isoformat()
            try:
                with Session(engine) as session:
                    run = session.get(SyncRun, run_id)
                    if run:
                        run.finished_at = datetime.now(timezone.utc)
                        run.found = p.found
                        run.indexed = p.indexed
                        run.skipped = p.skipped
                        run.deleted = p.deleted
                        run.failed = p.failed
                        session.add(run)
                        session.commit()
            except Exception:
                pass
            
            from .covers import start_prefetch_covers
            start_prefetch_covers(engine)

    def _sync(
        self, session: Session, run_id: int, only_root_id: Optional[int] = None
    ) -> None:
        p = self.progress
        roots = list(session.exec(select(RootFolder)).all())
        if only_root_id is not None:
            # "Rescan this folder only": limit scanning + deletion to one root.
            roots = [r for r in roots if r.id == only_root_id]
        rules = list(session.exec(select(FolderRule)).all())
        rules_by_root: Dict[int, Dict[str, List[str]]] = {}
        for r in rules:
            d = rules_by_root.setdefault(r.root_id, {"include": [], "exclude": []})
            d.setdefault(r.kind, []).append(r.subpath)

        existing: Dict[str, Book] = {
            b.abs_path: b for b in session.exec(select(Book)).all()
        }
        seen_paths = set()
        scanned_root_ids: set = set()
        new_files: List[tuple] = []  # (root_id, ScannedFile)

        for root in roots:
            if self._stop_event.is_set():
                raise SyncStopped()
            if not os.path.isdir(root.path):
                # Do NOT scan or delete books for an unavailable root — an
                # unmounted drive must never purge the library.
                self._record_error(
                    session,
                    run_id,
                    root.path,
                    "Root folder not found or not accessible — skipped, no books removed.",
                )
                continue
            scanned_root_ids.add(root.id)
            rr = rules_by_root.get(root.id, {"include": [], "exclude": []})

            def on_folder(folder: str):
                p.current_folder = folder

            for sf in scan_root(
                root.path,
                rr.get("include", []),
                rr.get("exclude", []),
                on_folder,
                self._stop_event.is_set,
            ):
                if self._stop_event.is_set():
                    raise SyncStopped()
                p.found += 1
                p.current_file = sf.filename
                seen_paths.add(sf.abs_path)
                book = existing.get(sf.abs_path)
                if book is None:
                    new_files.append((root.id, sf))
                elif book.size == sf.size and book.mtime == sf.mtime:
                    p.skipped += 1
                else:
                    self._update_changed(session, run_id, book, sf)
            if self._stop_event.is_set():
                raise SyncStopped()

        # Paths in DB but missing from disk: rename candidates, else deletions.
        # Only consider books whose root was actually scanned this run.
        missing = {
            path: book
            for path, book in existing.items()
            if path not in seen_paths and book.root_id in scanned_root_ids
        }
        missing_by_hash: Dict[str, List[Book]] = {}
        for book in missing.values():
            missing_by_hash.setdefault(book.file_hash, []).append(book)

        for root_id, sf in new_files:
            if self._stop_event.is_set():
                raise SyncStopped()
            p.current_file = sf.filename
            try:
                file_hash = partial_hash(sf.abs_path)
            except OSError as exc:
                p.failed += 1
                self._record_error(
                    session, run_id, sf.abs_path, f"Could not read file: {exc}"
                )
                continue
            candidates = missing_by_hash.get(file_hash)
            if candidates:
                # Rename/move: keep metadata, progress, bookmarks.
                book = candidates.pop(0)
                del missing[book.abs_path]
                book.abs_path = sf.abs_path
                book.root_id = root_id
                book.folder_path = sf.folder_path
                book.filename = sf.filename
                book.size = sf.size
                book.mtime = sf.mtime
                session.add(book)
                session.commit()
                p.indexed += 1
            else:
                self._insert_new(session, run_id, root_id, sf, file_hash)

        for book in missing.values():
            if self._stop_event.is_set():
                raise SyncStopped()
            self._delete_book(session, book)
            p.deleted += 1

        recompute_duplicates(session)
        search.rebuild_index(session)

    def _apply_extraction(
        self, session: Session, run_id: int, book: Book
    ) -> None:
        """Fill metadata gaps from embedded EPUB/PDF data. Covers are NOT
        rendered here — they are extracted lazily on first request (see
        services/covers.py) to keep sync fast. Failures never block indexing."""
        book.cover_state = "none" if book.format in ("txt", "html") else "pending"
        try:
            if book.format == "epub":
                ex = extract.extract_epub(book.abs_path)
            elif book.format == "pdf":
                ex = extract.extract_pdf_metadata(book.abs_path)
            else:
                return
        except extract.ExtractError as exc:
            self._record_error(
                session,
                run_id,
                book.abs_path,
                f"Indexed from filename only; embedded data unreadable: {exc}",
            )
            return

        # Keep the filename-derived cleaned_title as the default; store the
        # embedded title separately so the user can opt into it from Edit.
        book.meta_title = ex.title or None
        if ex.author and not book.cleaned_author:
            book.cleaned_author = ex.author
        if ex.series and not book.edited_series:
            book.edited_series = ex.series

    def _insert_new(
        self, session: Session, run_id: int, root_id: int, sf: ScannedFile, file_hash: str
    ) -> None:
        p = self.progress
        title, author = clean_filename(os.path.splitext(sf.filename)[0])
        book = Book(
            root_id=root_id,
            abs_path=sf.abs_path,
            folder_path=sf.folder_path,
            filename=sf.filename,
            format=sf.format,
            size=sf.size,
            mtime=sf.mtime,
            file_hash=file_hash,
            cleaned_title=title,
            cleaned_author=author,
        )
        session.add(book)
        session.commit()
        session.refresh(book)
        self._apply_extraction(session, run_id, book)
        session.add(book)
        session.commit()
        self._map_taxonomy(session, book)
        p.indexed += 1

    def _map_taxonomy(self, session: Session, book: Book) -> None:
        """Link a newly-indexed book to its first-class author + categories so
        it appears under Authors/Categories without needing a restart."""
        from . import categorize, taxonomy
        from ..models import BookAuthor, BookCategory

        name = (book.edited_author or book.cleaned_author or "").strip()
        if name:
            author = taxonomy.get_or_create_author(session, name)
            if not session.get(BookAuthor, (book.id, author.id)):
                session.add(BookAuthor(book_id=book.id, author_id=author.id))
        for cat_name in categorize.categorize_book(book):
            cat = taxonomy.get_or_create_category(session, cat_name)
            if not session.get(BookCategory, (book.id, cat.id)):
                session.add(BookCategory(book_id=book.id, category_id=cat.id))
        session.commit()

    def _update_changed(
        self, session: Session, run_id: int, book: Book, sf: ScannedFile
    ) -> None:
        p = self.progress
        try:
            book.file_hash = partial_hash(sf.abs_path)
        except OSError as exc:
            p.failed += 1
            self._record_error(
                session, run_id, sf.abs_path, f"Could not read changed file: {exc}"
            )
            return
        book.size = sf.size
        book.mtime = sf.mtime
        self._apply_extraction(session, run_id, book)
        session.add(book)
        session.commit()
        p.indexed += 1

    def _delete_book(self, session: Session, book: Book) -> None:
        if book.cover_path and os.path.isfile(book.cover_path):
            try:
                os.remove(book.cover_path)
            except OSError:
                pass
        session.delete(book)  # cascades to progress + bookmarks
        session.commit()


sync_manager = SyncManager()
