"""Intelligent default categories.

Rather than using raw folder names, classify each book into meaningful subject
categories by matching keywords against its title + folder path. A book can
match several categories. Used for the one-time startup seed and the on-demand
"regenerate" action.

Keywords are matched on WORD boundaries (not bare substrings), so e.g. "cloud"
does not match a sync folder named "CloudSync" and "go" does not match
"nihongo"/"tango". Boundaries treat letters, digits, '+' and '#' as
word characters, so "c++"/"c#" still match as whole tokens.
"""
import re
from typing import Dict, List, Optional, Pattern

from sqlmodel import Session, select

from ..models import Book, BookCategory
from .taxonomy import get_or_create_category

# Ordered category -> keyword list.
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "System Design": ["system design", "designing data", "scalability", "scalable",
                      "distributed system", "distributed systems", "microservice",
                      "microservices", "high availability", "load balancing",
                      "load balancer"],
    "System Architecture": ["architecture", "architect", "clean architecture",
                            "design pattern", "design patterns",
                            "patterns of enterprise", "ddd", "domain driven",
                            "domain-driven"],
    "Data Structures & Algorithms": ["algorithm", "algorithms", "data structure",
                                     "data structures", "leetcode",
                                     "cracking the coding", "competitive programming"],
    "Programming Languages": ["python", "javascript", "typescript", "java", "golang",
                             "go", "rust", "c++", "c#", "kotlin", "scala", "ruby",
                             "php", "haskell", "clojure", "swift"],
    "Web Development": ["web development", "react", "vue", "angular", "node", "nodejs",
                       "node.js", "django", "flask", "fastapi", "frontend",
                       "front-end", "backend", "back-end", "html", "css", "rest api",
                       "graphql"],
    "Databases": ["database", "databases", "sql", "postgres", "postgresql", "mysql",
                 "mongodb", "redis", "nosql", "data engineering", "data warehouse"],
    "Machine Learning & AI": ["machine learning", "deep learning", "neural network",
                             "neural networks", "artificial intelligence", "ai",
                             "data science", "tensorflow", "pytorch", "nlp",
                             "natural language", "llm", "transformer"],
    "DevOps & Cloud": ["devops", "kubernetes", "docker", "aws", "azure", "gcp",
                      "cloud", "terraform", "ci/cd", "site reliability", "sre"],
    "Operating Systems": ["operating system", "operating systems", "linux", "unix",
                         "kernel"],
    "Networking": ["networking", "network", "tcp/ip", "http", "protocol"],
    "Security": ["security", "cryptography", "cryptographic", "hacking",
                "penetration testing", "pentest", "cybersecurity", "malware"],
    "Mathematics": ["mathematics", "calculus", "algebra", "statistics",
                   "probability", "discrete math", "linear algebra"],
    "Career & Soft Skills": ["interview", "interviews", "career", "soft skill",
                            "soft skills", "productivity", "leadership",
                            "pragmatic programmer", "clean coder"],
    "Language Learning": ["jlpt", "toefl", "ielts", "nihongo", "hiragana", "katakana",
                         "kanji", "language learning", "grammar and workbook",
                         "vocabulary", "goethe"],
    "Fiction": ["novel", "novels", "light novel", "light novels", "fiction",
               "fantasy", "manga", "comic", "comics", "potter", "tolkien",
               "stormlight", "mistborn"],
}

# A "word" char for boundary purposes: letters, digits, and '+'/'#' so that
# c++ / c# match as whole tokens.
_BOUND = r"(?<![a-z0-9+#]){core}(?![a-z0-9+#])"


def _normalize(text: str) -> str:
    """Lowercase and reduce every run of non-word chars to a single space, so
    path separators, punctuation and camelCase-free tokens become comparable."""
    text = re.sub(r"[^a-z0-9+#]+", " ", text.lower())
    return f" {text} "


def _pattern(keyword: str) -> Optional[Pattern[str]]:
    parts = [re.escape(p) for p in _normalize(keyword).split() if p]
    if not parts:
        return None
    core = r"\s+".join(parts)
    return re.compile(_BOUND.format(core=core))


def _compile(mapping: Dict[str, List[str]]) -> Dict[str, List[Pattern[str]]]:
    out: Dict[str, List[Pattern[str]]] = {}
    for category, keywords in mapping.items():
        pats = [p for kw in keywords if (p := _pattern(kw)) is not None]
        out[category] = pats
    return out


_COMPILED = _compile(CATEGORY_KEYWORDS)


def classify(title: str, folder_path: str) -> List[str]:
    """Return the list of category names a book matches (possibly empty)."""
    haystack = _normalize(f"{title} {folder_path}")
    return [
        category
        for category, patterns in _COMPILED.items()
        if any(p.search(haystack) for p in patterns)
    ]


def categorize_book(book: Book) -> List[str]:
    # Leave books with no keyword match uncategorized rather than inventing
    # noisy folder-name categories.
    return classify(book.edited_title or book.cleaned_title or "", book.folder_path)


def regenerate(
    session: Session, *, only_if_empty: bool = False, replace: bool = False
) -> int:
    """(Re)assign categories for all books from the classifier. Returns number
    of (book, category) links created.

    - only_if_empty: do nothing if any links already exist (idempotent startup
      seed).
    - replace: delete all existing links first, so a regenerate fixes books that
      were previously mis-categorized (the classifier only ever adds links)."""
    if only_if_empty and session.exec(select(BookCategory).limit(1)).first():
        return 0

    if replace:
        for link in session.exec(select(BookCategory)).all():
            session.delete(link)
        session.commit()

    cache: dict[str, int] = {}
    links = 0
    for book in session.exec(select(Book)).all():
        names = categorize_book(book)
        for name in names:
            cid = cache.get(name)
            if cid is None:
                cid = get_or_create_category(session, name).id
                cache[name] = cid
            if not session.get(BookCategory, (book.id, cid)):
                session.add(BookCategory(book_id=book.id, category_id=cid))
                links += 1
    session.commit()
    return links
