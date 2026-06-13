import os

from sqlmodel import Session, select

from app.models import Book, Bookmark, ReadingProgress, RootFolder
from app.services.paths import normalize_root_path
from app.services.sync import SyncManager
from tests.conftest import make_epub


def seed(engine, tmp_path):
    lib = tmp_path / "library"
    (lib / "Novels").mkdir(parents=True)
    (lib / "Web").mkdir()
    make_epub(lib / "Novels" / "Jane Doe - First Book.epub",
              title="First Book", author="Jane Doe", cover=True)
    (lib / "Novels" / "second_book.txt").write_text("text content")
    (lib / "Web" / "guide.html").write_text(
        '<html><body><img src="img/pic.png"></body></html>'
    )
    (lib / "Web" / "img").mkdir()
    (lib / "Web" / "img" / "pic.png").write_bytes(b"\x89PNG fake")
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    manager = SyncManager()
    manager.start(engine)
    manager.wait()
    return lib


def test_library_grouped_by_folder(client, engine, tmp_path):
    seed(engine, tmp_path)
    data = client.get("/api/library").json()
    assert data["total"] == 3
    folders = [s["folder"] for s in data["sections"]]
    assert any(f.endswith("Novels") for f in folders)
    assert any(f.endswith("Web") for f in folders)
    novels = next(s for s in data["sections"] if s["folder"].endswith("Novels"))
    assert len(novels["books"]) == 2


def test_search_fields_and_empty_query(client, engine, tmp_path):
    seed(engine, tmp_path)
    assert client.get("/api/search", params={"q": "Jane"}).json()["books"]
    assert client.get("/api/search", params={"q": "second"}).json()["books"]
    # path search
    assert client.get("/api/search", params={"q": "Novels"}).json()["books"]
    r = client.get("/api/search", params={"q": "  "})
    assert r.status_code == 400
    assert "empty" in r.json()["detail"]


def test_metadata_edit_and_duplicate_recompute(client, engine, tmp_path):
    seed(engine, tmp_path)
    with Session(engine) as s:
        b1, b2 = s.exec(select(Book).order_by(Book.id).limit(2)).all()
        id1, id2 = b1.id, b2.id
    # Title via PATCH, author via the first-class authors endpoint.
    for bid in (id1, id2):
        client.patch(f"/api/books/{bid}", json={"edited_title": "Same Title"})
        client.put(f"/api/books/{bid}/authors", json={"names": ["Same Author"]})
    assert client.get(f"/api/books/{id1}").json()["is_duplicate"] is True
    assert client.get(f"/api/books/{id2}").json()["is_duplicate"] is True


def test_browse_authors_and_categories(client, engine, tmp_path):
    seed(engine, tmp_path)
    # Authors are linked during sync from the filename-derived author.
    authors = client.get("/api/browse/authors").json()["groups"]
    assert any(g["name"] == "Jane Doe" for g in authors)
    assert any(g["name"] == "Unknown" for g in authors)  # author-less books

    # Series is gone.
    assert client.get("/api/browse/series").status_code == 404

    # Create a category and assign a book; it shows up in browse + filters.
    with Session(engine) as s:
        bid = s.exec(select(Book).order_by(Book.id)).first().id
    cat = client.post("/api/categories", json={"name": "Tech"}).json()
    client.post(f"/api/categories/{cat['id']}/books/{bid}")
    cats = client.get("/api/browse/categories").json()["groups"]
    assert any(g["name"] == "Tech" and g["count"] == 1 for g in cats)
    assert "Tech" in client.get("/api/library/filters").json()["categories"]


def test_fts_search_prefix_and_ranking(client, engine, tmp_path):
    seed(engine, tmp_path)
    # prefix match: "Ja" should find "Jane Doe"
    hits = client.get("/api/search", params={"q": "Ja"}).json()["books"]
    assert any("First Book" == b["title"] for b in hits)
    # multi-term AND
    assert client.get("/api/search", params={"q": "first book"}).json()["books"]
    # path is searchable
    assert client.get("/api/search", params={"q": "Web"}).json()["books"]


def test_epub_locations_roundtrip(client, engine, tmp_path):
    seed(engine, tmp_path)
    with Session(engine) as s:
        bid = s.exec(select(Book).where(Book.format == "epub")).one().id
    assert client.get(f"/api/books/{bid}/epub-locations").json()["locations"] is None
    client.put(f"/api/books/{bid}/epub-locations",
               json={"locations": "[\"cfi1\",\"cfi2\"]"})
    assert client.get(f"/api/books/{bid}/epub-locations").json()["locations"] == \
        "[\"cfi1\",\"cfi2\"]"


def test_lazy_cover_endpoint(client, engine, tmp_path):
    seed(engine, tmp_path)
    with Session(engine) as s:
        epub = s.exec(select(Book).where(Book.format == "epub")).one()
        txt = s.exec(select(Book).where(Book.format == "txt")).one()
    # epub cover extracts on demand -> 200 image
    r = client.get(f"/api/books/{epub.id}/cover")
    assert r.status_code == 200 and "image" in r.headers["content-type"]
    # txt has no cover -> 404 with a clear message
    r = client.get(f"/api/books/{txt.id}/cover")
    assert r.status_code == 404


def test_open_updates_recent(client, engine, tmp_path):
    seed(engine, tmp_path)
    with Session(engine) as s:
        book_id = s.exec(select(Book)).first().id
    assert client.get("/api/recent").json()["books"] == []
    client.post(f"/api/books/{book_id}/open")
    recent = client.get("/api/recent").json()["books"]
    assert [b["id"] for b in recent] == [book_id]
    assert client.delete("/api/recent").json()["cleared"] == 1
    assert client.get("/api/recent").json()["books"] == []


def test_add_root_accepts_normalized_windows_path(client, tmp_path, monkeypatch):
    from app.api import roots as roots_api

    folder = tmp_path / "Books" / "Languages"
    folder.mkdir(parents=True)

    def fake_normalize(raw):
        assert raw == r"D:\Books\Languages"
        return str(folder)

    monkeypatch.setattr(roots_api, "normalize_root_path", fake_normalize)
    r = client.post("/api/roots", json={"path": r"D:\Books\Languages"})
    assert r.status_code == 201
    assert r.json()["path"] == str(folder)


def test_normalize_root_path_validates_basic_cases(tmp_path, monkeypatch):
    from app.services import paths as path_service

    existing = tmp_path / "books"
    existing.mkdir()
    book_file = tmp_path / "book.epub"
    book_file.write_text("x")
    real_isdir = path_service.os.path.isdir

    def fake_isdir(path):
        if path == "/mnt/d/Books":
            return True
        return real_isdir(path)

    monkeypatch.setattr(path_service.os.path, "isdir", fake_isdir)

    assert normalize_root_path(str(existing)) == str(existing)
    assert normalize_root_path(r"D:\Books") == "/mnt/d/Books"
    assert "folder path" in client_error(lambda: normalize_root_path("")).lower()
    assert "full folder path" in client_error(lambda: normalize_root_path("Books"))
    assert "not a file" in client_error(lambda: normalize_root_path(str(book_file)))
    assert "does not exist" in client_error(lambda: normalize_root_path(str(tmp_path / "missing")))


def client_error(fn):
    try:
        fn()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("expected ValueError")


def test_folder_filter_options_include_parents_and_match_subtree(client, engine, tmp_path):
    lib = tmp_path / "Library" / "Books"
    (lib / "Study" / "Tech" / "A").mkdir(parents=True)
    (lib / "Study" / "Tech" / "B").mkdir(parents=True)
    (lib / "Study" / "Tech" / "A" / "one.txt").write_text("one")
    (lib / "Study" / "Tech" / "B" / "two.txt").write_text("two")
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    manager = SyncManager()
    manager.start(engine)
    manager.wait()

    folders = client.get("/api/library/filters").json()["folders"]
    tech = next(f for f in folders if f["label"].endswith("Library / Books / Study / Tech"))
    data = client.get("/api/library", params=[("folder", tech["value"])]).json()
    assert data["total"] == 2


def test_progress_and_bookmarks_roundtrip(client, engine, tmp_path):
    seed(engine, tmp_path)
    with Session(engine) as s:
        book_id = s.exec(select(Book)).first().id
    assert client.get(f"/api/books/{book_id}/progress").json()["position"] is None
    client.put(f"/api/books/{book_id}/progress", json={"position": "12"})
    client.put(f"/api/books/{book_id}/progress", json={"position": "15"})
    assert client.get(f"/api/books/{book_id}/progress").json()["position"] == "15"

    bm = client.post(
        f"/api/books/{book_id}/bookmarks", json={"position": "epubcfi(/6/4!/2)"}
    ).json()
    assert client.get(f"/api/books/{book_id}/bookmarks").json()[0]["id"] == bm["id"]
    bookmarked = client.get("/api/bookmarks").json()["items"]
    assert bookmarked[0]["book"]["id"] == book_id
    assert bookmarked[0]["bookmark_count"] == 1
    client.delete(f"/api/bookmarks/{bm['id']}")
    assert client.get(f"/api/books/{book_id}/bookmarks").json() == []

    client.put(f"/api/books/{book_id}/progress", json={"position": "22"})
    client.post(f"/api/books/{book_id}/bookmarks", json={"position": "23"})
    cleared = client.delete(f"/api/books/{book_id}/reading-state").json()
    assert cleared == {"cleared_progress": True, "cleared_bookmarks": 1}
    assert client.get(f"/api/books/{book_id}/progress").json()["position"] is None
    assert client.get(f"/api/books/{book_id}/bookmarks").json() == []


def test_html_asset_containment(client, engine, tmp_path):
    lib = seed(engine, tmp_path)
    with Session(engine) as s:
        html_book = s.exec(select(Book).where(Book.format == "html")).one()
        book_id = html_book.id
    # index page + same-folder asset OK
    assert client.get(f"/api/books/{book_id}/html/").status_code == 200
    assert client.get(f"/api/books/{book_id}/html/img/pic.png").status_code == 200
    # escape attempts rejected
    (tmp_path / "secret.txt").write_text("secret")
    # httpx normalizes literal ../ client-side; server still must not serve it
    r = client.get(f"/api/books/{book_id}/html/../../secret.txt")
    assert r.status_code != 200
    r = client.get(f"/api/books/{book_id}/html/..%2F..%2Fsecret.txt")
    assert r.status_code in (403, 404)
    assert "secret" not in r.text


def test_file_serving_media_type(client, engine, tmp_path):
    seed(engine, tmp_path)
    with Session(engine) as s:
        epub = s.exec(select(Book).where(Book.format == "epub")).one()
    r = client.get(f"/api/books/{epub.id}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/epub+zip"


def test_missing_file_clear_error(client, engine, tmp_path):
    lib = seed(engine, tmp_path)
    with Session(engine) as s:
        book = s.exec(select(Book).where(Book.format == "txt")).one()
        book_id, path = book.id, book.abs_path
    os.remove(path)
    r = client.get(f"/api/books/{book_id}/file")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "sync" in detail.lower()
    assert "/mnt/" not in detail and str(tmp_path) not in detail


def test_sync_conflict_409(client, engine, tmp_path, monkeypatch):
    # Simulate a running sync on the global manager.
    import threading

    from app.api import sync as sync_api

    started = threading.Event()
    release = threading.Event()

    class Fake:
        def start(self, _engine, only_root_id=None):
            from app.services.sync import SyncAlreadyRunning

            raise SyncAlreadyRunning()

    monkeypatch.setattr(sync_api, "sync_manager", Fake())
    r = client.post("/api/sync")
    assert r.status_code == 409
    assert "already running" in r.json()["detail"]


def test_sync_stop_endpoint(client, monkeypatch):
    from app.api import sync as sync_api

    class Fake:
        def stop(self):
            return True

    monkeypatch.setattr(sync_api, "sync_manager", Fake())
    assert client.post("/api/sync/stop").json() == {"stopping": True}
