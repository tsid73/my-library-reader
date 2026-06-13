import os

from app.services.extract import ExtractError, render_pdf_cover
from app.services.hashing import partial_hash
from app.services.safe_paths import resolve_inside
from app.services.scanner import folder_allowed
from app.services.titles import clean_filename, looks_like_author, normalize


class TestTitleCleanup:
    def test_underscores_and_whitespace(self):
        assert clean_filename("the_pragmatic__programmer") == (
            "the pragmatic programmer",
            None,
        )

    def test_author_dash_title(self):
        title, author = clean_filename(
            "Brandon Sanderson - The Way of Kings"
        )
        assert title == "The Way of Kings"
        assert author == "Brandon Sanderson"

    def test_title_dash_author(self):
        title, author = clean_filename("A Storm of Swords - George Martin")
        assert title == "A Storm of Swords"
        assert author == "George Martin"

    def test_ambiguous_dash_kept_whole(self):
        # Both sides look like titles -> keep everything.
        title, author = clean_filename(
            "Algorithms and Data Structures - Advanced Topics in Programming"
        )
        assert author is None
        assert "Algorithms and Data Structures" in title
        assert "Advanced Topics" in title

    def test_digits_not_author(self):
        title, author = clean_filename("Python 101 - Part 2")
        assert author is None

    def test_looks_like_author(self):
        assert looks_like_author("J.K. Rowling")
        assert not looks_like_author("the way of kings")
        assert not looks_like_author("Chapter 12")

    def test_normalize(self):
        assert normalize("The Way of Kings!") == "the way of kings"
        assert normalize(None) == ""


class TestFolderRules:
    def test_no_rules_includes_all(self):
        assert folder_allowed("Study/Tech", [], [])

    def test_exclude_wins_over_include(self):
        assert not folder_allowed("Study/Tech", ["Study"], ["Study/Tech"])

    def test_include_limits(self):
        assert folder_allowed("Novels/Fantasy", ["Novels"], [])
        assert not folder_allowed("Study", ["Novels"], [])

    def test_case_insensitive(self):
        assert not folder_allowed("study/TECH", [], ["Study/Tech"])


class TestPartialHash:
    def test_changes_with_content(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hello")
        h1 = partial_hash(str(f))
        f.write_text("hello world")
        assert partial_hash(str(f)) != h1


class TestPdfCoverExtraction:
    def test_corrupt_pdf_raises_clean_error_without_mupdf_noise(self, tmp_path, capfd):
        bad_pdf = tmp_path / "bad.pdf"
        bad_pdf.write_bytes(b"%PDF-1.4\nnot a real pdf\n")

        try:
            render_pdf_cover(str(bad_pdf))
        except ExtractError as exc:
            assert "Could not render PDF first page" in str(exc)
        else:
            raise AssertionError("expected ExtractError")

        captured = capfd.readouterr()
        assert "MuPDF error" not in captured.err
        assert "startxref" not in captured.err

    def test_large_file_tail_matters(self, tmp_path):
        f = tmp_path / "big.bin"
        data = bytearray(os.urandom(3 * 1024 * 1024))
        f.write_bytes(data)
        h1 = partial_hash(str(f))
        data[-1] ^= 0xFF  # change last byte only
        f.write_bytes(data)
        assert partial_hash(str(f)) != h1


class TestSafePaths:
    def test_inside_ok(self, tmp_path):
        book_dir = tmp_path / "book"
        book_dir.mkdir()
        (book_dir / "img.png").write_bytes(b"x")
        assert resolve_inside(str(book_dir), "img.png") is not None

    def test_traversal_blocked(self, tmp_path):
        book_dir = tmp_path / "book"
        book_dir.mkdir()
        (tmp_path / "secret.txt").write_text("nope")
        assert resolve_inside(str(book_dir), "../secret.txt") is None

    def test_symlink_escape_blocked(self, tmp_path):
        book_dir = tmp_path / "book"
        book_dir.mkdir()
        (tmp_path / "secret.txt").write_text("nope")
        link = book_dir / "link.txt"
        os.symlink(tmp_path / "secret.txt", link)
        assert resolve_inside(str(book_dir), "link.txt") is None
