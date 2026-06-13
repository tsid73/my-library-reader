import re
from typing import Optional, Tuple

_WHITESPACE = re.compile(r"\s+")
# A word that looks like part of a person's name: "Brandon", "J.K.", "O'Brien", "García"
_NAME_WORD = re.compile(r"^[A-Z][\w'.\-]*$", re.UNICODE)


def looks_like_author(text: str) -> bool:
    words = text.split()
    if not 1 <= len(words) <= 3:
        return False
    if any(ch.isdigit() for ch in text):
        return False
    return all(_NAME_WORD.match(w) for w in words)


def clean_filename(stem: str) -> Tuple[str, Optional[str]]:
    """Conservative filename -> (title, author or None).

    Only splits on ' - ' when exactly one side confidently looks like an
    author name; otherwise the whole cleaned string is kept as the title.
    """
    s = stem.replace("_", " ")
    s = _WHITESPACE.sub(" ", s).strip()
    if not s:
        return stem, None

    parts = [p.strip() for p in s.split(" - ")]
    if len(parts) == 2 and all(parts):
        left, right = parts
        left_is_author = looks_like_author(left)
        right_is_author = looks_like_author(right)
        if left_is_author and not right_is_author:
            return right, left
        if right_is_author and not left_is_author:
            return left, right
    return s, None


def normalize(text: Optional[str]) -> str:
    """Normalization used for duplicate detection."""
    if not text:
        return ""
    s = re.sub(r"[^\w\s]", " ", text.casefold(), flags=re.UNICODE)
    return _WHITESPACE.sub(" ", s).strip()
