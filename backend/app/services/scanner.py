import os
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional

from .. import config


@dataclass
class ScannedFile:
    abs_path: str
    folder_path: str
    filename: str
    format: str
    size: int
    mtime: float


def _norm(rel: str) -> str:
    # Windows-mounted paths are case-insensitive, so compare rules that way too.
    return rel.replace("\\", "/").strip("/").casefold()


def _is_under(rel: str, sub: str) -> bool:
    return rel == sub or rel.startswith(sub + "/")


def folder_allowed(rel_folder: str, includes: List[str], excludes: List[str]) -> bool:
    """Exclude wins over include. With no include rules everything is included."""
    rel = _norm(rel_folder)
    if any(_is_under(rel, _norm(e)) for e in excludes):
        return False
    if includes:
        return any(_is_under(rel, _norm(i)) for i in includes)
    return True


def _worth_descending(rel_folder: str, includes: List[str], excludes: List[str]) -> bool:
    rel = _norm(rel_folder)
    if any(_is_under(rel, _norm(e)) for e in excludes):
        return False
    if includes:
        # Descend if this folder is under an include, or is an ancestor of one.
        return any(
            _is_under(rel, _norm(i)) or _is_under(_norm(i), rel) or rel == ""
            for i in includes
        )
    return True


def scan_root(
    root_path: str,
    includes: List[str],
    excludes: List[str],
    on_folder: Optional[Callable[[str], None]] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Iterator[ScannedFile]:
    root_path = os.path.abspath(root_path)
    for dirpath, dirnames, filenames in os.walk(root_path):
        if should_stop and should_stop():
            return
        rel_folder = os.path.relpath(dirpath, root_path)
        if rel_folder == ".":
            rel_folder = ""
        # Prune subdirectories not worth walking into.
        dirnames[:] = [
            d
            for d in sorted(dirnames)
            if _worth_descending(os.path.join(rel_folder, d), includes, excludes)
        ]
        if on_folder:
            on_folder(dirpath)
        if not folder_allowed(rel_folder, includes, excludes):
            continue
        for name in sorted(filenames):
            if should_stop and should_stop():
                return
            ext = os.path.splitext(name)[1].lower()
            if ext not in config.SUPPORTED_EXTENSIONS:
                continue
            abs_path = os.path.join(dirpath, name)
            try:
                st = os.stat(abs_path)
            except OSError:
                continue
            yield ScannedFile(
                abs_path=abs_path,
                folder_path=dirpath,
                filename=name,
                format=config.format_for_extension(ext),
                size=st.st_size,
                mtime=st.st_mtime,
            )
