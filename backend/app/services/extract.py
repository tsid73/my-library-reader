"""Embedded metadata + cover extraction for EPUB and PDF.

All functions raise ExtractError with a human-readable, actionable message;
callers index the book anyway (filename-derived title) and record the error.
"""
import io
from dataclasses import dataclass
from typing import Optional

from .. import config


class ExtractError(Exception):
    pass


@dataclass
class Extracted:
    title: Optional[str] = None
    author: Optional[str] = None
    cover_bytes: Optional[bytes] = None  # raw image data, any format


def _quiet_pymupdf(fitz) -> None:
    tools = getattr(fitz, "TOOLS", None)
    if tools is None:
        return
    for name in ("mupdf_display_errors", "mupdf_display_warnings"):
        fn = getattr(tools, name, None)
        if fn is not None:
            try:
                fn(False)
            except Exception:
                pass


def extract_epub(path: str) -> Extracted:
    try:
        import ebooklib
        from ebooklib import epub

        book = epub.read_epub(path, options={"ignore_ncx": True})
    except Exception as exc:
        raise ExtractError(f"Could not parse EPUB: {exc}") from exc

    result = Extracted()
    try:
        titles = book.get_metadata("DC", "title")
        if titles:
            result.title = str(titles[0][0]).strip() or None
        creators = book.get_metadata("DC", "creator")
        if creators:
            result.author = str(creators[0][0]).strip() or None
    except Exception:
        pass  # metadata is optional; cover may still work

    cover_item = None
    try:
        covers = list(book.get_items_of_type(ebooklib.ITEM_COVER))
        if covers:
            cover_item = covers[0]
        else:
            # Fall back to an image item flagged as cover in OPF metadata,
            # else the first image in the book.
            images = list(book.get_items_of_type(ebooklib.ITEM_IMAGE))
            meta_cover = book.get_metadata("OPF", "cover")
            if meta_cover:
                cover_id = meta_cover[0][1].get("content")
                for item in images:
                    if item.id == cover_id:
                        cover_item = item
                        break
            if cover_item is None and images:
                cover_item = images[0]
        if cover_item is not None:
            result.cover_bytes = cover_item.get_content()
    except Exception:
        pass
    return result


def extract_pdf_metadata(path: str) -> Extracted:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path)
        meta = reader.metadata
    except Exception as exc:
        raise ExtractError(f"Could not parse PDF: {exc}") from exc

    result = Extracted()
    if meta:
        if meta.title and meta.title.strip():
            result.title = meta.title.strip()
        if meta.author and meta.author.strip():
            result.author = meta.author.strip()
    return result


def render_pdf_cover(path: str) -> bytes:
    """Render page 1 as the cover."""
    try:
        import fitz  # PyMuPDF

        _quiet_pymupdf(fitz)
        with fitz.open(path) as doc:
            if doc.page_count == 0:
                raise ExtractError("PDF has no pages to use as a cover")
            page = doc.load_page(0)
            zoom = 150 / 72
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return pix.tobytes("jpeg")
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError(f"Could not render PDF first page: {exc}") from exc


def save_cover(image_bytes: bytes, dest_path: str) -> None:
    """Normalize any image bytes to a resized JPEG at dest_path. Hardened
    against decompression bombs and truncated/corrupt image data so a single
    bad cover can never stall or crash the sync."""
    try:
        from PIL import Image, ImageFile
        from PIL import features  # noqa: F401  (ensures plugins are registered)

        # Cap pixel count to defuse decompression-bomb images.
        Image.MAX_IMAGE_PIXELS = 64_000_000  # ~64 MP
        # Allow Pillow to load slightly truncated streams instead of raising.
        ImageFile.LOAD_TRUNCATED_IMAGES = True

        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.load()
        except Image.DecompressionBombError as exc:
            raise ExtractError(f"Cover image too large (possible bomb): {exc}")

        img = img.convert("RGB")
        if img.width > config.COVER_MAX_WIDTH:
            ratio = config.COVER_MAX_WIDTH / img.width
            img = img.resize(
                (config.COVER_MAX_WIDTH, max(1, int(img.height * ratio)))
            )
        img.save(dest_path, "JPEG", quality=config.COVER_JPEG_QUALITY)
    except ExtractError:
        raise
    except Exception as exc:
        raise ExtractError(f"Could not save cover image: {exc}") from exc
