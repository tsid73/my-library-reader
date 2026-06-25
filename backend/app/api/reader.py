import mimetypes
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from ..db import get_session
from ..models import RootFolder
from ..services.paths import relative_display
from ..services.safe_paths import resolve_inside
from .books import get_book

router = APIRouter()

MEDIA_TYPES = {
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
    "txt": "text/plain; charset=utf-8",
    "html": "text/html; charset=utf-8",
}


def _safe(book, session: Session) -> str:
    roots = [r.path for r in session.exec(select(RootFolder)).all()]
    return relative_display(book.abs_path, roots)


@router.get("/books/{book_id}/file")
@router.get("/books/{book_id}/file.epub")
def book_file(book_id: int, session: Session = Depends(get_session)):
    book = get_book(book_id, session)
    if not os.path.isfile(book.abs_path):
        raise HTTPException(
            404,
            detail=f"File is missing on disk: {_safe(book, session)}. "
            "Run a sync to update the library.",
        )
    return FileResponse(
        book.abs_path, media_type=MEDIA_TYPES.get(book.format, "application/octet-stream")
    )


# HTML books are served under /html/ so that relative asset URLs inside the
# document (images, CSS) resolve back to this same route.
@router.get("/books/{book_id}/html/")
def html_index(book_id: int, session: Session = Depends(get_session)):
    book = get_book(book_id, session)
    if book.format != "html":
        raise HTTPException(400, detail="This route only serves HTML books.")
    if not os.path.isfile(book.abs_path):
        raise HTTPException(
            404, detail=f"File is missing on disk: {_safe(book, session)}."
        )
    return FileResponse(book.abs_path, media_type="text/html; charset=utf-8")


@router.get("/books/{book_id}/html/{asset_path:path}")
def html_asset(
    book_id: int, asset_path: str, session: Session = Depends(get_session)
):
    book = get_book(book_id, session)
    if book.format != "html":
        raise HTTPException(400, detail="This route only serves HTML books.")
    resolved = resolve_inside(book.folder_path, asset_path)
    if resolved is None:
        raise HTTPException(
            403,
            detail="Asset is outside the book's folder and cannot be served.",
        )
    media_type = mimetypes.guess_type(resolved)[0] or "application/octet-stream"
    return FileResponse(resolved, media_type=media_type)
