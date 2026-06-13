"""Intelligent default categories.

Rather than using raw folder names, classify each book into meaningful subject
categories by matching keywords against its title + folder path. A book can
match several categories. Used for the one-time startup seed and the on-demand
"regenerate" action.
"""
import re
from typing import Dict, List

from sqlmodel import Session, select

from ..models import Book, BookCategory
from .taxonomy import get_or_create_category

# Ordered category -> keyword list. Keywords are matched case-insensitively on
# word boundaries against "<title> <folder path>".
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "System Design": ["system design", "designing data", "scalab", "distributed system",
                      "microservice", "high availability", "load balanc"],
    "System Architecture": ["architecture", "architect", "clean architecture",
                            "design pattern", "patterns of enterprise", "ddd",
                            "domain driven", "domain-driven"],
    "Data Structures & Algorithms": ["algorithm", "data structure", "leetcode",
                                     "cracking the coding", "competitive programming"],
    "Programming Languages": ["python", "javascript", "typescript", "java ", "golang",
                             " go ", "rust", "c++", "c#", "kotlin", "scala", "ruby",
                             "php", "haskell", "clojure", "swift"],
    "Web Development": ["web develop", "react", "vue", "angular", "node", "django",
                       "flask", "fastapi", "frontend", "front-end", "backend",
                       "back-end", "html", "css", "rest api", "graphql"],
    "Databases": ["database", "sql", "postgres", "mysql", "mongodb", "redis",
                 "nosql", "data engineering", "data warehouse"],
    "Machine Learning & AI": ["machine learning", "deep learning", "neural network",
                             "artificial intelligence", " ai ", "data science",
                             "tensorflow", "pytorch", "nlp", "natural language",
                             "llm", "transformer"],
    "DevOps & Cloud": ["devops", "kubernetes", "docker", "aws", "azure", "gcp",
                      "cloud", "terraform", "ci/cd", "site reliability", "sre"],
    "Operating Systems": ["operating system", "linux", "unix", "kernel", "os dev"],
    "Networking": ["network", "tcp/ip", "http", "protocol"],
    "Security": ["security", "cryptograph", "hacking", "penetration", "pentest",
                "cyber", "malware"],
    "Mathematics": ["mathematics", "calculus", "algebra", "statistics",
                   "probability", "discrete math", "linear algebra"],
    "Career & Soft Skills": ["interview", "career", "soft skill", "productivity",
                            "manager", "leadership", "pragmatic programmer",
                            "clean coder"],
    "Fiction": ["novel", "fiction", "fantasy", "potter", "tolkien", "stormlight",
               "mistborn"],
}


def classify(title: str, folder_path: str) -> List[str]:
    """Return the list of category names a book matches (possibly empty)."""
    haystack = f" {title} {folder_path} ".lower().replace("\\", "/").replace("/", " ")
    haystack = re.sub(r"\s+", " ", haystack)
    matched: List[str] = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.strip() in haystack:
                matched.append(category)
                break
    return matched


def categorize_book(book: Book) -> List[str]:
    names = classify(book.edited_title or book.cleaned_title or "", book.folder_path)
    if names:
        return names
    # Fallback: the top-level folder name under the library, if meaningful.
    parts = [p for p in book.folder_path.replace("\\", "/").split("/") if p]
    # Skip a leading "mnt" + drive letter (WSL mount).
    if len(parts) >= 2 and parts[0] == "mnt" and len(parts[1]) == 1:
        parts = parts[2:]
    return []  # leave uncategorized rather than inventing noisy folder categories


def regenerate(session: Session, *, only_if_empty: bool = False) -> int:
    """(Re)assign categories for all books from the classifier. Returns number
    of (book, category) links created. With only_if_empty, does nothing if any
    category links already exist (used for the idempotent startup seed)."""
    if only_if_empty and session.exec(select(BookCategory).limit(1)).first():
        return 0

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
