import type { Theme } from "./common";
import { THEME_BG } from "./common";

// HTML books are served from /api/books/{id}/html/ so relative asset URLs
// (images, CSS) resolve back through the path-restricted asset route.
export default function HtmlReader({
  bookId,
  theme,
}: {
  bookId: number;
  theme: Theme;
}) {
  return (
    <div className="html-viewport" style={{ background: THEME_BG[theme] }}>
      <iframe
        className="html-frame"
        src={`/api/books/${bookId}/html/`}
        title="HTML book"
        sandbox="allow-same-origin"
      />
    </div>
  );
}
