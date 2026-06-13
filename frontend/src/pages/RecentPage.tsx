import { useEffect, useState } from "react";
import { del, get } from "../api/client";
import BookCard from "../components/BookCard";
import MetadataModal from "../components/MetadataModal";
import { confirmAction, toastError } from "../lib/alerts";
import type { BookCard as BookCardT } from "../types";

export default function RecentPage() {
  const [books, setBooks] = useState<BookCardT[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<BookCardT | null>(null);

  const load = () => {
    setError(null);
    return get<{ books: BookCardT[] }>("/recent")
      .then((r) => setBooks(r.books))
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const clearRecent = async () => {
    if (!(await confirmAction("Clear recent files?",
      "This clears your recently-opened list. Books and progress are kept.",
      "Clear"))) return;
    try {
      await del("/recent");
      setBooks([]);
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  return (
    <main className="page">
      <div className="page-head">
        <h2 className="folder-heading">Recently opened</h2>
        {books.length > 0 && (
          <button className="btn danger" onClick={clearRecent}>
            Clear recent files
          </button>
        )}
      </div>
      {loading && <p className="hint">Loading…</p>}
      {error && <p className="error-text">{error}</p>}
      {!loading && !error && books.length === 0 && (
        <p className="hint">Nothing opened yet. Open a book from the Library.</p>
      )}
      <div className="grid">
        {books.map((b) => (
          <BookCard key={b.id} book={b} onEdit={setEditing} />
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
