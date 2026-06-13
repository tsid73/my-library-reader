import io

from sqlmodel import Session, select

from app.models import Author, Book, BookCategory, Category, RootFolder
from app.services import categorize
from app.services.sync import SyncManager
from tests.conftest import make_epub, make_pdf


def run_sync(engine):
    m = SyncManager()
    m.start(engine)
    m.wait()
    return m.progress


def build_library(engine, tmp_path):
    lib = tmp_path / "library"
    (lib / "Study" / "Tech").mkdir(parents=True)
    (lib / "Novels").mkdir(parents=True)
    make_pdf(lib / "Study" / "Tech" / "Designing Data-Intensive Applications.pdf",
             title="Designing Data-Intensive Applications")
    make_epub(lib / "Novels" / "Brandon Sanderson - Mistborn.epub",
              title="Mistborn", author="Brandon Sanderson", cover=True)
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)
    return lib


# ---- classifier ----
class TestClassifier:
    def test_keyword_matches(self):
        assert "System Design" in categorize.classify(
            "Designing Data-Intensive Applications", "/books/tech")
        assert "Programming Languages" in categorize.classify("Fluent Python", "/x")
        assert "System Architecture" in categorize.classify("Clean Architecture", "/x")
        assert "Machine Learning & AI" in categorize.classify(
            "Deep Learning with PyTorch", "/x")

    def test_no_false_match(self):
        assert categorize.classify("A Quiet Walk", "/random") == []


# ---- seeding idempotency ----
def test_category_seed_idempotent(engine, tmp_path):
    build_library(engine, tmp_path)
    with Session(engine) as s:
        first = categorize.regenerate(s, only_if_empty=True)
        assert first == 0  # sync already mapped categories for new books
    # books got at least one category during sync
    with Session(engine) as s:
        assert s.exec(select(BookCategory).limit(1)).first() is not None


# ---- author CRUD + merge ----
def test_author_crud_and_merge(client, engine, tmp_path):
    build_library(engine, tmp_path)
    authors = client.get("/api/authors").json()
    # Brandon Sanderson was linked during sync.
    assert any(a["name"] == "Brandon Sanderson" and a["count"] == 1 for a in authors)

    a1 = client.post("/api/authors", json={"name": "B. Sanderson"}).json()
    with Session(engine) as s:
        bid = s.exec(select(Book).where(Book.format == "epub")).one().id
    client.post(f"/api/authors/{a1['id']}/books/{bid}")
    # merge the duplicate into the canonical author
    canonical = next(a for a in client.get("/api/authors").json()
                     if a["name"] == "Brandon Sanderson")
    r = client.post(f"/api/authors/{a1['id']}/merge",
                    json={"into_id": canonical["id"]})
    assert r.status_code == 200
    names = [a["name"] for a in client.get("/api/authors").json()]
    assert "B. Sanderson" not in names  # merged away
    detail = client.get(f"/api/books/{bid}").json()
    assert any(a["name"] == "Brandon Sanderson" for a in detail["authors"])


# ---- category CRUD + assign + filter ----
def test_category_crud_assign_and_filter(client, engine, tmp_path):
    build_library(engine, tmp_path)
    with Session(engine) as s:
        epub = s.exec(select(Book).where(Book.format == "epub")).one().id

    cat = client.post("/api/categories", json={"name": "Favourites"}).json()
    assert cat["count"] == 0
    client.post(f"/api/categories/{cat['id']}/books/{epub}")

    # rename
    client.patch(f"/api/categories/{cat['id']}", json={"name": "Faves"})
    listing = client.get("/api/categories").json()
    fav = next(c for c in listing if c["id"] == cat["id"])
    assert fav["name"] == "Faves" and fav["count"] == 1

    # library filter by category returns only the assigned book
    lib = client.get("/api/library", params={"category": "Faves"}).json()
    ids = [b["id"] for s in lib["sections"] for b in s["books"]]
    assert ids == [epub]

    # delete clears the link
    client.delete(f"/api/categories/{cat['id']}")
    with Session(engine) as s:
        assert s.exec(select(BookCategory).where(
            BookCategory.category_id == cat["id"])).first() is None


def test_duplicate_category_rejected(client, engine, tmp_path):
    build_library(engine, tmp_path)
    client.post("/api/categories", json={"name": "Dup"})
    r = client.post("/api/categories", json={"name": "Dup"})
    assert r.status_code == 409


# ---- cover upload / reset ----
def test_cover_upload_and_reset(client, engine, tmp_path):
    build_library(engine, tmp_path)
    with Session(engine) as s:
        txt_book = make_pdf  # noqa  (silence linters about unused import path)
        bid = s.exec(select(Book).where(Book.format == "pdf")).one().id

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (120, 180), (10, 120, 90)).save(buf, "PNG")
    buf.seek(0)
    r = client.post(
        f"/api/books/{bid}/cover",
        files={"file": ("cover.png", buf, "image/png")},
    )
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.get(Book, bid).cover_state == "ok"
    assert client.get(f"/api/books/{bid}/cover").status_code == 200

    # non-image is rejected
    bad = client.post(
        f"/api/books/{bid}/cover",
        files={"file": ("x.txt", io.BytesIO(b"nope"), "text/plain")},
    )
    assert bad.status_code == 400

    # reset → re-extract on next request
    client.delete(f"/api/books/{bid}/cover")
    with Session(engine) as s:
        assert s.get(Book, bid).cover_state == "pending"
