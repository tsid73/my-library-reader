import { useState } from "react";
import type { BookCard as BookCardT } from "../types";

const PLACEHOLDER_COLORS = [
  "#5b4d8a",
  "#8a4d5b",
  "#4d8a5b",
  "#4d6b8a",
  "#8a6b4d",
  "#6b4d8a",
];

function placeholderColor(title: string): string {
  let h = 0;
  for (const ch of title) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return PLACEHOLDER_COLORS[Math.abs(h) % PLACEHOLDER_COLORS.length];
}

export default function BookCard({
  book,
  onEdit,
}: {
  book: BookCardT;
  onEdit?: (book: BookCardT) => void;
}) {
  const [coverFailed, setCoverFailed] = useState(false);
  const displayTitle = book.is_duplicate
    ? `${book.title} (Duplicate)`
    : book.title;
  const showCover = book.has_cover && !coverFailed;

  return (
    <div className="book-card">
      <a
        className="cover-link"
        href={`/read/${book.id}`}
        target="_blank"
        rel="noopener"
        title={displayTitle}
      >
        {showCover ? (
          <img
            className="cover"
            src={`/api/books/${book.id}/cover`}
            alt={displayTitle}
            loading="lazy"
            onError={() => setCoverFailed(true)}
          />
        ) : (
          <div
            className="cover placeholder"
            style={{ background: placeholderColor(book.title) }}
          >
            <span className="placeholder-title">{book.title}</span>
          </div>
        )}
        <span className="format-badge">{book.format.toUpperCase()}</span>
        {onEdit && (
          <button
            className="edit-btn"
            title="Edit metadata"
            onClick={(e) => {
              e.preventDefault();
              onEdit(book);
            }}
          >
            ✎
          </button>
        )}
      </a>
      <div className="book-title" title={displayTitle}>
        {displayTitle}
      </div>
      {book.author && (
        <div className="book-author" title={book.author}>
          {book.author}
        </div>
      )}
    </div>
  );
}
