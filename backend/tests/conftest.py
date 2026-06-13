import os
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    # Point cover cache at a temp dir so tests never touch real data/.
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "COVERS_DIR", tmp_path / "data" / "covers")
    eng = db.init_engine(tmp_path / "test.db")
    db.create_tables(eng)
    return eng


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client(engine):
    app = create_app()
    return TestClient(app)


def make_epub(path, title="Test Title", author="Test Author", cover=False):
    """Build a minimal valid EPUB by hand."""
    cover_meta = '<meta name="cover" content="cov"/>' if cover else ""
    cover_item = (
        '<item id="cov" href="cover.jpg" media-type="image/jpeg"/>' if cover else ""
    )
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:identifier id="id">test-book</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>en</dc:language>
    {cover_meta}
  </metadata>
  <manifest>
    <item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {cover_item}
  </manifest>
  <spine toc="ncx"><itemref idref="c1"/></spine>
</package>"""
    ncx = """<?xml version="1.0"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="test-book"/></head>
  <docTitle><text>t</text></docTitle>
  <navMap><navPoint id="n1" playOrder="1"><navLabel><text>c1</text></navLabel>
  <content src="c1.xhtml"/></navPoint></navMap>
</ncx>"""
    chapter = (
        '<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml">'
        "<head><title>c1</title></head><body><p>Hello world.</p></body></html>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        z.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="content.opf" '
            'media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        z.writestr("content.opf", opf)
        z.writestr("toc.ncx", ncx)
        z.writestr("c1.xhtml", chapter)
        if cover:
            from PIL import Image
            import io

            buf = io.BytesIO()
            Image.new("RGB", (60, 90), (120, 40, 40)).save(buf, "JPEG")
            z.writestr("cover.jpg", buf.getvalue())


def make_pdf(path, title=None):
    """Build a minimal one-page PDF via PyMuPDF."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello PDF")
    if title:
        doc.set_metadata({"title": title})
    doc.save(str(path))
    doc.close()
