"""Live end-to-end smoke test against a running backend (http://127.0.0.1:8011).
Run after a sync has indexed some books. Not part of the pytest suite."""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8011/api"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return r.status, (json.loads(r.read() or "null"))


def head(method, path):
    req = urllib.request.Request(BASE + path, method=method)
    with urllib.request.urlopen(req) as r:
        return r.status, r.headers.get("content-type")


def main():
    ok = True

    # Pick a PDF/EPUB with a cover.
    _, lib = call("GET", "/library?sort=title")
    book = None
    for sec in lib["sections"]:
        for b in sec["books"]:
            if b["format"] in ("pdf", "epub") and b["has_cover"]:
                book = b
                break
        if book:
            break
    assert book, "no pdf/epub with cover found"
    bid = book["id"]
    print(f"[library] total={lib['total']} sections={len(lib['sections'])}")
    print(f"[book] id={bid} fmt={book['format']} title={book['title'][:50]!r}")

    # progress roundtrip
    call("PUT", f"/books/{bid}/progress", {"position": "7"})
    _, prog = call("GET", f"/books/{bid}/progress")
    assert prog["position"] == "7", prog
    print(f"[progress] saved/restored -> {prog['position']}")

    # bookmarks
    _, bm = call("POST", f"/books/{bid}/bookmarks", {"position": "7"})
    _, lst = call("GET", f"/books/{bid}/bookmarks")
    assert any(x["id"] == bm["id"] for x in lst)
    call("DELETE", f"/bookmarks/{bm['id']}")
    _, lst2 = call("GET", f"/books/{bid}/bookmarks")
    assert all(x["id"] != bm["id"] for x in lst2)
    print(f"[bookmarks] add/list/delete ok (had {len(lst)}, now {len(lst2)})")

    # file + cover serving
    st, ct = head("GET", f"/books/{bid}/file")
    print(f"[file] status={st} type={ct}")
    assert st == 200
    st, ct = head("GET", f"/books/{bid}/cover")
    print(f"[cover] status={st} type={ct}")
    assert st == 200 and "image" in ct

    # open -> recent
    call("POST", f"/books/{bid}/open")
    _, rec = call("GET", "/recent")
    assert any(b["id"] == bid for b in rec["books"])
    print(f"[recent] book appears after open (recent={len(rec['books'])})")

    # metadata edit -> duplicate recompute on two books sharing title+author
    secbooks = [b for s in lib["sections"] for b in s["books"]][:2]
    if len(secbooks) == 2:
        for b in secbooks:
            call("PATCH", f"/books/{b['id']}",
                 {"edited_title": "ZZ Dup", "edited_author": "ZZ Author"})
        _, d = call("GET", f"/books/{secbooks[0]['id']}")
        assert d["is_duplicate"] is True, d
        print("[metadata] edit + duplicate recompute ok")
        # revert
        for b in secbooks:
            call("PATCH", f"/books/{b['id']}",
                 {"edited_title": None, "edited_author": None})

    print("\nALL SMOKE CHECKS PASSED" if ok else "FAILURES")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("SMOKE FAIL:", e)
        sys.exit(1)
