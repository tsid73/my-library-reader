import os
from typing import Optional


def resolve_inside(folder: str, relative: str) -> Optional[str]:
    """Resolve `relative` against `folder` and return the real path only if it
    stays inside `folder` (symlink escapes and `..` traversal are rejected).
    Returns None when the path escapes or does not exist."""
    base = os.path.realpath(folder)
    candidate = os.path.realpath(os.path.join(base, relative))
    if candidate != base and not candidate.startswith(base + os.sep):
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate
