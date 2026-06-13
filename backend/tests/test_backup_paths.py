from sqlmodel import Session, select

from app.models import Book, RootFolder
from app.services.paths import relative_display
from app.services.sync import SyncManager
from tests.conftest import make_epub, make_pdf


def run_sync(engine, only_root_id=None):
    m = SyncManager()
    m.start(engine, only_root_id=only_root_id)
    m.wait()
    return m.progress


def build(engine, tmp_path):
    lib = tmp_path / "Books"
    (lib / "Study" / "Tech").mkdir(parents=True)
    make_pdf(lib / "Study" / "Tech" / "algorithms.pdf", title="Algorithms")
    make_epub(lib / "Study" / "Mistborn.epub", title="Mistborn", author="Sanderson")
    with Session(engine) as s:
        s.add(RootFolder(path=str(lib)))
        s.commit()
    run_sync(engine)
    return lib


# ---- path sanitization ----
def test_relative_display_strips_machine_prefix():
    roots = ["/mnt/d/Mega/Books"]
    assert relative_display("/mnt/d/Mega/Books/Study/x.pdf", roots) == "Books/Study/x.pdf"
    # unknown root → mount prefix still stripped
    assert relative_display("/mnt/d/Other/y.pdf", []) == "Other/y.pdf"


def test_reader_missing_file_error_is_sanitized(client, engine, tmp_path):
    lib = build(engine, tmp_path)
    with Session(engine) as s:
        book = s.exec(select(Book).where(Book.format == "pdf")).one()
        bid, path = book.id, book.abs_path
    import os

    os.remove(path)
    r = client.get(f"/api/books/{bid}/file")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "/mnt/" not in detail and str(tmp_path) not in detail
    assert "Books/Study/Tech/algorithms.pdf" in detail


def test_sync_error_paths_are_relative(client, engine, tmp_path):
    # An offline root produces an error; its path must be sanitized in the API.
    # Drive sync through the API so /sync/status reflects the global manager.
    import shutil
    import time

    missing = tmp_path / "Books"
    missing.mkdir()
    with Session(engine) as s:
        s.add(RootFolder(path=str(missing)))
        s.commit()
    shutil.rmtree(missing)

    client.post("/api/sync")
    for _ in range(50):
        if not client.get("/api/sync/status").json()["running"]:
            break
        time.sleep(0.1)
    status = client.get("/api/sync/status").json()
    assert status["errors"]
    assert all(str(tmp_path) not in e["file_path"] for e in status["errors"])
    assert all("/mnt/" not in e["file_path"] for e in status["errors"])


# ---- rescan one root ----
def test_rescan_single_root(client, engine, tmp_path):
    lib = build(engine, tmp_path)
    # add a second root, then rescan only the first — second's books untouched
    other = tmp_path / "Other"
    other.mkdir()
    make_pdf(other / "solo.pdf", title="Solo")
    with Session(engine) as s:
        s.add(RootFolder(path=str(other)))
        first_id = s.exec(select(RootFolder).order_by(RootFolder.id)).first().id
        s.commit()
    # rescan first root only: 'solo.pdf' (in other root) is not discovered/added
    r = client.post(f"/api/roots/{first_id}/rescan")
    assert r.status_code == 202
    import time

    time.sleep(0.1)
    # wait for completion
    for _ in range(50):
        if not client.get("/api/sync/status").json()["running"]:
            break
        time.sleep(0.1)
    titles = {b["title"] for s in client.get("/api/library").json()["sections"]
              for b in s["books"]}
    assert "Algorithms" in titles
    assert "Solo" not in titles  # other root was not scanned


# ---- export / import ----
def test_export_import_roundtrip(client, engine, tmp_path):
    build(engine, tmp_path)
    with Session(engine) as s:
        epub = s.exec(select(Book).where(Book.format == "epub")).one().id
    client.patch(f"/api/books/{epub}", json={"edited_title": "My Mistborn"})
    client.put(f"/api/books/{epub}/categories", json={"names": ["Fantasy"]})
    client.put(f"/api/books/{epub}/progress", json={"position": "epubcfi(/6/4)"})
    client.post(f"/api/books/{epub}/bookmarks", json={"position": "epubcfi(/6/8)"})

    dump = client.get("/api/export").json()
    assert dump["version"] == 1
    assert any(b["edited_title"] == "My Mistborn" for b in dump["books"])

    # wipe user data then re-import
    client.delete(f"/api/books/{epub}/reading-state")
    client.patch(f"/api/books/{epub}", json={"edited_title": ""})
    res = client.post("/api/import", json=dump).json()
    assert res["matched"] >= 1

    detail = client.get(f"/api/books/{epub}").json()
    assert detail["edited_title"] == "My Mistborn"
    assert any(c["name"] == "Fantasy" for c in detail["categories"])
    assert client.get(f"/api/books/{epub}/progress").json()["position"] == "epubcfi(/6/4)"
    assert len(client.get(f"/api/books/{epub}/bookmarks").json()) == 1
