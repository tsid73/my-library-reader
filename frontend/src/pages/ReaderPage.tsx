import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { del, get, post, put } from "../api/client";
import EpubReader, { EpubMode } from "../readers/EpubReader";
import HtmlReader from "../readers/HtmlReader";
import PdfReader, { PdfMode } from "../readers/PdfReader";
import TextReader from "../readers/TextReader";
import { confirmAction } from "../lib/alerts";
import type { ReaderHandle, Theme } from "../readers/common";
import type { Bookmark, BookDetail, ProgressInfo } from "../types";

export default function ReaderPage() {
  const { id } = useParams();
  const bookId = Number(id);
  const [book, setBook] = useState<BookDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [initialPos, setInitialPos] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [resetKey, setResetKey] = useState(0);
  const openedRef = useRef<number | null>(null);

  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("reader.theme") as Theme) || "light"
  );
  const [fontSize, setFontSize] = useState(
    () => Number(localStorage.getItem("reader.font")) || 100
  );
  const [zoom, setZoom] = useState(
    () => Number(localStorage.getItem("reader.zoom")) || 1.2
  );
  const [pdfMode, setPdfMode] = useState<PdfMode>(
    () => (localStorage.getItem("reader.pdfMode") as PdfMode) || "scroll"
  );
  const [epubMode, setEpubMode] = useState<EpubMode>(
    () => (localStorage.getItem("reader.epubMode") as EpubMode) || "paged"
  );
  const [pageInfo, setPageInfo] = useState({ page: 0, total: 0 });
  const [epubLabel, setEpubLabel] = useState("");
  const [pdfJump, setPdfJump] = useState<{ page: number } | null>(null);
  // Wrap each jump in a fresh object so re-selecting the same page (e.g.
  // clicking the same bookmark twice, or jumping to the page you're on) still
  // re-triggers the reader's jump effect.
  const requestPdfJump = (page: number) => setPdfJump({ page });
  // Paged-mode page box: edit freely and jump only on Enter or blur. Jumping on
  // every keystroke would render each intermediate page while you type (e.g.
  // 1, then 15, then 150 for "150").
  const [pageInput, setPageInput] = useState("1");
  useEffect(() => {
    setPageInput(String(pageInfo.page || 1));
  }, [pageInfo.page]);
  const commitPageInput = () => {
    const n = parseInt(pageInput, 10);
    if (Number.isFinite(n)) requestPdfJump(n);
    else setPageInput(String(pageInfo.page || 1));
  };
  const [jumpCfi, setJumpCfi] = useState<string | null>(null);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [showBookmarks, setShowBookmarks] = useState(false);

  const handleRef = useRef<ReaderHandle>(null);
  const saveTimer = useRef<number | null>(null);
  const hasProgress = book?.format === "pdf" || book?.format === "epub";

  useEffect(() => localStorage.setItem("reader.theme", theme), [theme]);
  useEffect(
    () => localStorage.setItem("reader.font", String(fontSize)),
    [fontSize]
  );
  useEffect(() => localStorage.setItem("reader.zoom", String(zoom)), [zoom]);
  useEffect(
    () => localStorage.setItem("reader.pdfMode", pdfMode),
    [pdfMode]
  );
  useEffect(
    () => localStorage.setItem("reader.epubMode", epubMode),
    [epubMode]
  );

  useEffect(() => {
    (async () => {
      try {
        const detail = await get<BookDetail>(`/books/${bookId}`);
        setBook(detail);
        document.title = detail.title;
        if (openedRef.current !== bookId) {
          openedRef.current = bookId;
          await post(`/books/${bookId}/open`);
        }
        if (detail.format === "pdf" || detail.format === "epub") {
          const prog = await get<ProgressInfo>(`/books/${bookId}/progress`);
          setInitialPos(prog.position);
          setBookmarks(await get<Bookmark[]>(`/books/${bookId}/bookmarks`));
        }
        setLoaded(true);
      } catch (e) {
        setError((e as Error).message);
      }
    })();
  }, [bookId]);

  const saveProgress = (position: string) => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      put(`/books/${bookId}/progress`, { position }).catch(() => {});
    }, 800);
  };

  // Flush the latest position when the tab is hidden or closed. The debounced
  // save above can otherwise be dropped if you close the reader within 800ms of
  // the last move; `keepalive` lets the request finish as the page unloads.
  useEffect(() => {
    if (!hasProgress) return;
    const flush = () => {
      const pos = handleRef.current?.currentPosition();
      if (!pos) return;
      try {
        fetch(`/api/books/${bookId}/progress`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position: pos }),
          keepalive: true,
        });
      } catch {
        /* best effort */
      }
    };
    const onVisibility = () => {
      if (document.visibilityState === "hidden") flush();
    };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [hasProgress, bookId]);

  const addBookmark = async () => {
    const pos = handleRef.current?.currentPosition();
    if (!pos) return;
    const label = prompt("Enter a label for this bookmark (optional):");
    if (label === null) return;
    try {
      const bm = await post<Bookmark>(`/books/${bookId}/bookmarks`, {
        position: pos,
        label: label.trim() || undefined,
      });
      setBookmarks((b) => [...b, bm]);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const removeBookmark = async (bmId: number) => {
    await del(`/bookmarks/${bmId}`);
    setBookmarks((b) => b.filter((x) => x.id !== bmId));
  };

  const resetReadingState = async () => {
    if (!(await confirmAction(
      "Reset this book?",
      "Clears its bookmarks and last-read position. The book itself is untouched.",
      "Reset"))) return;
    try {
      await del(`/books/${bookId}/reading-state`);
      setBookmarks([]);
      setInitialPos(null);
      requestPdfJump(1);
      setJumpCfi(null);
      setEpubLabel("");
      setResetKey((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const jumpToBookmark = (pos: string) => {
    if (book?.format === "pdf") requestPdfJump(parseInt(pos, 10));
    else setJumpCfi(pos + "#" + Date.now());
  };

  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  };

  if (error) return <div className="reader-error">{error}</div>;
  if (!book || !loaded) return <div className="reader-loading">Loading...</div>;

  const fontControls = (
    <div className="ctrl-group">
      <button
        className="icon-btn"
        title="Smaller text"
        onClick={() => setFontSize((f) => Math.max(60, f - 10))}
      >
        A-
      </button>
      <span className="ctrl-value">{fontSize}%</span>
      <button
        className="icon-btn"
        title="Larger text"
        onClick={() => setFontSize((f) => Math.min(220, f + 10))}
      >
        A+
      </button>
    </div>
  );

  return (
    <div className="reader-page" data-theme={theme}>
      <div className="reader-toolbar">
        <a className="reader-back" href="/" title="Back to library">
          Back
        </a>
        <span className="reader-title" title={book.title}>
          {book.title}
        </span>

        <div className="reader-controls">
          {book.format === "pdf" && (
            <>
              <div className="seg">
                <button
                  className={pdfMode === "scroll" ? "seg-on" : ""}
                  onClick={() => setPdfMode("scroll")}
                  title="Continuous scroll"
                >
                  Scroll
                </button>
                <button
                  className={pdfMode === "paged" ? "seg-on" : ""}
                  onClick={() => setPdfMode("paged")}
                  title="One page at a time"
                >
                  Paged
                </button>
              </div>
              {pdfMode === "paged" && (
                <div className="ctrl-group">
                  <button
                    className="icon-btn"
                    onClick={() => requestPdfJump(pageInfo.page - 1)}
                  >
                    Prev
                  </button>
                  <input
                    className="page-input"
                    type="number"
                    min={1}
                    max={pageInfo.total || undefined}
                    value={pageInput}
                    onChange={(e) => setPageInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter")
                        (e.target as HTMLInputElement).blur();
                    }}
                    onBlur={commitPageInput}
                  />
                  <span className="ctrl-value">/ {pageInfo.total}</span>
                  <button
                    className="icon-btn"
                    onClick={() => requestPdfJump(pageInfo.page + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
              {pdfMode === "scroll" && (
                <span className="ctrl-value">
                  Page {pageInfo.page} / {pageInfo.total}
                </span>
              )}
              <div className="ctrl-group">
                <button
                  className="icon-btn"
                  title="Zoom out"
                  onClick={() =>
                    setZoom((z) => Math.max(0.4, +(z - 0.2).toFixed(2)))
                  }
                >
                  -
                </button>
                <span className="ctrl-value">{Math.round(zoom * 100)}%</span>
                <button
                  className="icon-btn"
                  title="Zoom in"
                  onClick={() =>
                    setZoom((z) => Math.min(4, +(z + 0.2).toFixed(2)))
                  }
                >
                  +
                </button>
              </div>
            </>
          )}

          {book.format === "epub" && (
            <>
              <div className="seg">
                <button
                  className={epubMode === "paged" ? "seg-on" : ""}
                  onClick={() => setEpubMode("paged")}
                >
                  Paged
                </button>
                <button
                  className={epubMode === "scroll" ? "seg-on" : ""}
                  onClick={() => setEpubMode("scroll")}
                >
                  Scroll
                </button>
              </div>
              {epubLabel && <span className="ctrl-value">{epubLabel}</span>}
              {fontControls}
            </>
          )}

          {book.format === "txt" && fontControls}

          <select
            className="theme-select"
            value={theme}
            onChange={(e) => setTheme(e.target.value as Theme)}
            title="Theme"
          >
            <option value="light">Light</option>
            <option value="sepia">Sepia</option>
            <option value="dark">Dark</option>
          </select>

          {hasProgress && (
            <>
              <button
                className="icon-btn wide"
                onClick={addBookmark}
                title="Bookmark current position"
              >
                Bookmark
              </button>
              <button
                className={`icon-btn wide ${showBookmarks ? "active" : ""}`}
                onClick={() => setShowBookmarks((v) => !v)}
                title="Show bookmarks"
              >
                Saved {bookmarks.length}
              </button>
              <button
                className="icon-btn wide danger"
                onClick={resetReadingState}
                title="Clear bookmarks and last position"
              >
                Reset
              </button>
            </>
          )}
          <button className="icon-btn" onClick={toggleFullscreen} title="Fullscreen">
            Full
          </button>
        </div>
      </div>

      <div className="reader-body">
        {showBookmarks && hasProgress && (
          <aside className="bookmark-sidebar">
            <h4>Bookmarks</h4>
            {bookmarks.length === 0 && (
              <p className="hint">No bookmarks yet.</p>
            )}
            <ul>
              {bookmarks.map((bm) => (
                <li key={bm.id}>
                  <button
                    className="bm-jump"
                    onClick={() => jumpToBookmark(bm.position)}
                  >
                    {bm.label || (book.format === "pdf"
                      ? `Page ${bm.position}`
                      : "Saved location")}
                  </button>
                  <button
                    className="icon-btn small"
                    onClick={() => removeBookmark(bm.id)}
                    title="Delete bookmark"
                  >
                    x
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        )}

        <div className="reader-stage">
          {book.format === "pdf" && (
            <PdfReader
              key={`pdf-${resetKey}`}
              ref={handleRef}
              bookId={bookId}
              initialPosition={initialPos}
              zoom={zoom}
              theme={theme}
              mode={pdfMode}
              jumpTo={pdfJump}
              onPageChange={(page, total) => {
                setPageInfo({ page, total });
                saveProgress(String(page));
              }}
            />
          )}
          {book.format === "epub" && (
            <EpubReader
              key={`epub-${resetKey}`}
              ref={handleRef}
              bookId={bookId}
              initialPosition={initialPos}
              fontSize={fontSize}
              theme={theme}
              mode={epubMode}
              jumpToCfi={jumpCfi}
              onLocationChange={(label) => {
                setEpubLabel(label);
                const pos = handleRef.current?.currentPosition();
                if (pos) saveProgress(pos);
              }}
            />
          )}
          {book.format === "txt" && (
            <TextReader bookId={bookId} fontSize={fontSize} theme={theme} />
          )}
          {book.format === "html" && (
            <HtmlReader bookId={bookId} theme={theme} />
          )}
        </div>
      </div>
    </div>
  );
}
