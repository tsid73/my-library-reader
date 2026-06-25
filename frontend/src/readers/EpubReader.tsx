import ePub, { Book, Rendition } from "epubjs";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import type { ReaderHandle, Theme } from "./common";
import { THEME_BG, THEME_FG } from "./common";

export type EpubMode = "paged" | "scroll";

interface Props {
  bookId: number;
  initialPosition: string | null;
  fontSize: number;
  theme: Theme;
  mode: EpubMode;
  onLocationChange: (label: string) => void;
  jumpToCfi: string | null;
}

const EpubReader = forwardRef<ReaderHandle, Props>(function EpubReader(
  { bookId, initialPosition, fontSize, theme, mode, onLocationChange, jumpToCfi },
  ref
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bookRef = useRef<Book | null>(null);
  const renditionRef = useRef<Rendition | null>(null);
  const cfiRef = useRef<string | null>(initialPosition);
  // Keep latest font/theme in refs so re-renders use current values.
  const fontRef = useRef(fontSize);
  const themeRef = useRef(theme);
  const locationsReady = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useImperativeHandle(ref, () => ({
    currentPosition: () => cfiRef.current,
  }));

  const applyTheme = (r: Rendition) => {
    r.themes.register("reader", {
      body: {
        background: THEME_BG[themeRef.current],
        color: `${THEME_FG[themeRef.current]} !important`,
        padding: "8px 4px",
      },
      p: { color: `${THEME_FG[themeRef.current]} !important`, "line-height": "1.6" },
      a: { color: `${THEME_FG[themeRef.current]} !important` },
    });
    r.themes.select("reader");
    r.themes.fontSize(`${fontRef.current}%`);
  };

  const updateLabel = (cfi: string | null, displayed?: any) => {
    const book = bookRef.current;
    if (cfi && book && locationsReady.current && book.locations.length()) {
      const pct = Math.round((book.locations.percentageFromCfi(cfi) || 0) * 100);
      onLocationChange(`${pct}%`);
      return;
    }
    const page = displayed?.page;
    const total = displayed?.total;
    onLocationChange(page && total ? `Page ${page} / ${total}` : "");
  };

  // Build (or rebuild) the rendition for the current flow mode.
  const renderWithMode = async (m: EpubMode) => {
    const book = bookRef.current;
    const container = containerRef.current;
    if (!book || !container) return;
    if (renditionRef.current) {
      try {
        renditionRef.current.destroy();
      } catch {
        /* ignore */
      }
    }
    const rendition = book.renderTo(container, {
      width: "100%",
      height: "100%",
      spread: m === "scroll" ? "none" : "auto",
      flow: m === "scroll" ? "scrolled-doc" : "paginated",
    });
    renditionRef.current = rendition;
    applyTheme(rendition);
    rendition.on("relocated", (location: any) => {
      cfiRef.current = location.start.cfi;
      updateLabel(location.start.cfi, location.start.displayed);
    });
    await rendition.display(cfiRef.current || undefined);
  };

  // Load the book once; (re)render happens here and on mode change.
  useEffect(() => {
    let cancelled = false;
    let book: Book | null = null;

    (async () => {
      try {
        book = ePub(`/api/books/${bookId}/file.epub`);
        bookRef.current = book;
        await renderWithMode(mode);
        if (cancelled) return;
        setLoading(false);

        // Load cached locations (or generate once) for a % indicator.
        book.ready
          .then(async () => {
            try {
              const cached = await (
                await fetch(`/api/books/${bookId}/epub-locations`)
              ).json();
              if (cached.locations) {
                book!.locations.load(cached.locations);
              } else {
                await book!.locations.generate(1600);
                fetch(`/api/books/${bookId}/epub-locations`, {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ locations: book!.locations.save() }),
                }).catch(() => {});
              }
              locationsReady.current = true;
              updateLabel(cfiRef.current); // refresh to % once we can map it
            } catch {
              /* indicator is optional */
            }
          })
          .catch(() => {});
      } catch (e) {
        if (!cancelled)
          setError(
            `Could not open this EPUB: ${(e as Error).message}. The file may be corrupt.`
          );
      }
    })();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") renditionRef.current?.next();
      if (e.key === "ArrowLeft") renditionRef.current?.prev();
    };
    window.addEventListener("keydown", onKey);

    return () => {
      cancelled = true;
      window.removeEventListener("keydown", onKey);
      try {
        book?.destroy();
      } catch {
        /* ignore */
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId]);

  // Font/theme: apply in place (epub.js reflows) — no full re-display, no flicker.
  useEffect(() => {
    fontRef.current = fontSize;
    themeRef.current = theme;
    if (renditionRef.current) applyTheme(renditionRef.current);
  }, [fontSize, theme]);

  // Flow change: rebuild the rendition (runtime flow() alone doesn't relayout).
  useEffect(() => {
    if (bookRef.current && renditionRef.current) renderWithMode(mode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  useEffect(() => {
    if (jumpToCfi && renditionRef.current)
      renditionRef.current.display(jumpToCfi.split("#")[0]);
  }, [jumpToCfi]);

  if (error) return <div className="reader-error">{error}</div>;
  return (
    <div className="epub-viewport" style={{ background: THEME_BG[theme] }}>
      <button
        className="epub-nav left"
        hidden={mode === "scroll"}
        onClick={() => renditionRef.current?.prev()}
        aria-label="Previous page"
      >
        ‹
      </button>
      <div className="epub-stage">
        {loading && <div className="reader-loading-inline">Opening EPUB…</div>}
        <div ref={containerRef} className="epub-container" />
      </div>
      <button
        className="epub-nav right"
        hidden={mode === "scroll"}
        onClick={() => renditionRef.current?.next()}
        aria-label="Next page"
      >
        ›
      </button>
    </div>
  );
});

export default EpubReader;
