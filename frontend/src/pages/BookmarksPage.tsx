import { useEffect, useState } from "react";
import { get } from "../api/client";
import BookCard from "../components/BookCard";
import MetadataModal from "../components/MetadataModal";
import type { BookCard as BookCardT, BookmarkedBook } from "../types";

export default function BookmarksPage() {
  const [items, setItems] = useState<BookmarkedBook[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<BookCardT | null>(null);

  const load = () => {
    setError(null);
    return get<{ items: BookmarkedBook[] }>("/bookmarks")
      .then((r) => setItems(r.items))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <main className="page">
      <h2 className="folder-heading">Bookmarks</h2>
      {loading && <p className="hint">Loading…</p>}
      {error && <p className="error-text">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <p className="hint">
          No bookmarked books yet. Add bookmarks while reading a PDF or EPUB.
        </p>
      )}
      <div className="grid">
        {items.map((item) => (
          <div className="bookmarked-card" key={item.book.id}>
            <BookCard book={item.book} onEdit={setEditing} />
            <span className="bookmark-count">
              {item.bookmark_count} bookmark{item.bookmark_count === 1 ? "" : "s"}
            </span>
          </div>
        ))}
      </div>
      {editing && (
        <MetadataModal
          bookId={editing.id}
          onClose={() => setEditing(null)}
          onSaved={load}
        />
      )}
    </main>
  );
}
