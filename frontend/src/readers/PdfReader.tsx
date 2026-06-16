import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { ReaderHandle, Theme } from "./common";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export type PdfMode = "paged" | "scroll";

interface Props {
  bookId: number;
  initialPosition: string | null;
  zoom: number;
  theme: Theme;
  mode: PdfMode;
  onPageChange: (page: number, total: number) => void;
  // Wrapped in an object so the same target page re-triggers a jump.
  jumpTo: { page: number } | null;
}

const PdfReader = forwardRef<ReaderHandle, Props>(function PdfReader(
  { bookId, initialPosition, zoom, theme, mode, onPageChange, jumpTo },
  ref
) {
  const docRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null);
  const pageRef = useRef(1);
  const scrollRootRef = useRef<HTMLDivElement>(null);
  // Paged-mode single canvas.
  const pagedCanvasRef = useRef<HTMLCanvasElement>(null);
  const pagedTaskRef = useRef<pdfjsLib.RenderTask | null>(null);
  // Scroll-mode per-page canvases + render bookkeeping.
  const pageCanvases = useRef<Map<number, HTMLCanvasElement>>(new Map());
  const renderedPages = useRef<Set<number>>(new Set());
  // Live intersection ratio per page; the most-visible page is the one we save.
  const pageRatios = useRef<Map<number, number>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  // Width/height ratio of page 1, used to size scroll slots up-front so the
  // page placeholders don't all start short and jump as they render.
  const [pageAspect, setPageAspect] = useState(0.72);
  const [basePageSize, setBasePageSize] = useState({ width: 720, height: 1000 });
  const bg = theme === "light" ? "#525659" : "#111";

  useImperativeHandle(ref, () => ({
    currentPosition: () => String(pageRef.current),
  }));

  // ---------- shared load ----------
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const doc = await pdfjsLib.getDocument(`/api/books/${bookId}/file`)
          .promise;
        if (cancelled) return;
        docRef.current = doc;
        try {
          const p1 = await doc.getPage(1);
          if (cancelled) return;
          const vp = p1.getViewport({ scale: 1 });
          setPageAspect(vp.width / vp.height);
          setBasePageSize({ width: vp.width, height: vp.height });
        } catch {
          /* keep default aspect */
        }
        const start = initialPosition ? parseInt(initialPosition, 10) : 1;
        pageRef.current = Number.isFinite(start)
          ? Math.min(Math.max(1, start), doc.numPages)
          : 1;
        // Set total LAST: it triggers the render/restore effects, which must
        // already see the restored pageRef and the real page geometry to land
        // on the right page instead of page 1 with a default aspect ratio.
        setTotal(doc.numPages);
        onPageChange(pageRef.current, doc.numPages);
      } catch (e) {
        setError(
          `Could not open this PDF: ${(e as Error).message}. The file may be corrupt.`
        );
      }
    })();
    return () => {
      cancelled = true;
      pagedTaskRef.current?.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId]);

  // ---------- paged mode ----------
  const renderPaged = async (num: number) => {
    const doc = docRef.current;
    const canvas = pagedCanvasRef.current;
    if (!doc || !canvas) return;
    num = Math.min(Math.max(1, num), doc.numPages);
    pageRef.current = num;
    const page = await doc.getPage(num);
    const viewport = page.getViewport({ scale: zoom });
    const dpr = window.devicePixelRatio || 1;
    const renderViewport = page.getViewport({ scale: zoom * dpr });
    const ctx = canvas.getContext("2d")!;
    canvas.width = renderViewport.width;
    canvas.height = renderViewport.height;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    pagedTaskRef.current?.cancel();
    const task = page.render({ canvasContext: ctx, viewport: renderViewport });
    pagedTaskRef.current = task;
    try {
      await task.promise;
    } catch (e) {
      if ((e as Error)?.name !== "RenderingCancelledException") throw e;
    }
    onPageChange(num, doc.numPages);
  };

  useEffect(() => {
    if (mode === "paged" && docRef.current) renderPaged(pageRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, zoom, total]);

  // ---------- scroll mode ----------
  const renderScrollPage = async (num: number) => {
    const doc = docRef.current;
    const canvas = pageCanvases.current.get(num);
    if (!doc || !canvas || renderedPages.current.has(num)) return;
    renderedPages.current.add(num);
    const page = await doc.getPage(num);
    const viewport = page.getViewport({ scale: zoom });
    const dpr = window.devicePixelRatio || 1;
    const renderViewport = page.getViewport({ scale: zoom * dpr });
    const ctx = canvas.getContext("2d")!;
    canvas.width = renderViewport.width;
    canvas.height = renderViewport.height;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    await page.render({ canvasContext: ctx, viewport: renderViewport }).promise;
  };

  // Bring a page to the top of the scroll view. Re-asserts across frames so the
  // position stays correct after the target page renders and its slot settles to
  // its real height (otherwise the scroll drifts by ~a page).
  const scrollToPage = (num: number) => {
    const root = scrollRootRef.current;
    if (!root) return;
    pageRef.current = num;
    renderScrollPage(num);
    const align = () => {
      const target = root.querySelector(
        `.pdf-page-slot[data-page="${num}"]`
      ) as HTMLElement | null;
      if (target) root.scrollTop = target.offsetTop;
    };
    align();
    requestAnimationFrame(() => {
      align();
      requestAnimationFrame(align);
    });
  };

  useEffect(() => {
    if (mode !== "scroll" || !docRef.current || !scrollRootRef.current) return;
    const root = scrollRootRef.current;
    renderedPages.current.clear();
    pageRatios.current.clear();

    // Lazily render pages as they approach the viewport.
    const lazy = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const n = Number((e.target as HTMLElement).dataset.page);
            renderScrollPage(n);
          }
        }
      },
      { root, rootMargin: "600px 0px" }
    );
    // Track the most-visible page for progress saving. Each callback only
    // carries the slots whose visibility changed, so we keep a running ratio map
    // of all pages and pick the global maximum — otherwise the saved page lags
    // by one as you scroll.
    const tracker = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          const n = Number((e.target as HTMLElement).dataset.page);
          pageRatios.current.set(n, e.isIntersecting ? e.intersectionRatio : 0);
        }
        let best = pageRef.current;
        let bestRatio = 0;
        for (const [n, ratio] of pageRatios.current) {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            best = n;
          }
        }
        if (bestRatio > 0 && best !== pageRef.current) {
          pageRef.current = best;
          onPageChange(best, docRef.current!.numPages);
        }
      },
      { root, threshold: [0, 0.25, 0.5, 0.75, 1] }
    );
    const slots = root.querySelectorAll(".pdf-page-slot");
    slots.forEach((s) => {
      lazy.observe(s);
      tracker.observe(s);
    });
    // Restore scroll to the saved page.
    scrollToPage(pageRef.current);

    return () => {
      lazy.disconnect();
      tracker.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, total, zoom]);

  // ---------- external jump ----------
  useEffect(() => {
    if (jumpTo == null) return;
    if (mode === "paged") renderPaged(jumpTo.page);
    else scrollToPage(jumpTo.page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpTo]);

  // ---------- keyboard (paged only) ----------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (mode !== "paged") return;
      if (e.key === "ArrowRight" || e.key === "PageDown")
        renderPaged(pageRef.current + 1);
      if (e.key === "ArrowLeft" || e.key === "PageUp")
        renderPaged(pageRef.current - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // Re-bind on zoom so arrow-key navigation renders at the current zoom
    // (renderPaged closes over zoom).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, zoom]);

  if (error) return <div className="reader-error">{error}</div>;

  if (mode === "scroll") {
    return (
      <div className="pdf-scroll" ref={scrollRootRef} style={{ background: bg }}>
        {Array.from({ length: total }, (_, i) => i + 1).map((n) => (
          <div
            key={n}
            className="pdf-page-slot"
            data-page={n}
            style={{
              aspectRatio: String(pageAspect),
              minHeight: "unset",
              width: `${basePageSize.width * zoom}px`,
            }}
            ref={(el) => {
              const c = el?.querySelector("canvas") as HTMLCanvasElement | null;
              if (c) pageCanvases.current.set(n, c);
            }}
          >
            <canvas />
            <span className="pdf-page-num">{n}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div
      className="pdf-viewport"
      style={{ background: bg }}
      onClick={(e) => {
        const x = e.clientX - e.currentTarget.getBoundingClientRect().left;
        if (x > e.currentTarget.clientWidth / 2)
          renderPaged(pageRef.current + 1);
        else renderPaged(pageRef.current - 1);
      }}
    >
      <canvas ref={pagedCanvasRef} />
    </div>
  );
});

export default PdfReader;
