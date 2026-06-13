import Swal from "sweetalert2";
import { useCallback, useEffect, useState } from "react";
import { del, get, patch, post } from "../api/client";
import { confirmAction, promptText, toastError } from "../lib/alerts";
import BookCard from "../components/BookCard";
import MetadataModal from "../components/MetadataModal";
import type { BookCard as BookCardT, BrowseResponse, Entity } from "../types";

interface Props {
  kind: "categories" | "authors";
  label: string; // singular, e.g. "Category"
}

export default function ManageEntitiesPage({ kind, label }: Props) {
  const [groups, setGroups] = useState<BrowseResponse["groups"]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [newName, setNewName] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<BookCardT | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const browseKind = kind; // /browse/categories or /browse/authors

  const load = useCallback(() => {
    setError(null);
    Promise.all([
      get<BrowseResponse>(`/browse/${browseKind}`).then((r) => setGroups(r.groups)),
      get<Entity[]>(`/${kind}`).then(setEntities),
    ])
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [kind, browseKind]);

  useEffect(() => {
    load();
    setExpanded(new Set());
  }, [load]);

  const create = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await post(`/${kind}`, { name });
      setNewName("");
      load();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const rename = async (id: number, current: string) => {
    const name = await promptText(`Rename ${label.toLowerCase()}`, current);
    if (!name || name === current) return;
    try {
      await patch(`/${kind}/${id}`, { name });
      load();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const remove = async (id: number, name: string) => {
    if (!(await confirmAction(`Delete "${name}"?`,
      `This removes the ${label.toLowerCase()} and unassigns it from all books. Books are not deleted.`,
      "Delete"))) return;
    try {
      await del(`/${kind}/${id}`);
      load();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const merge = async (id: number, name: string) => {
    const targets = entities.filter((e) => e.id !== id);
    if (!targets.length) return;
    const res = await Swal.fire({
      background: "#161922",
      color: "#e9ebf0",
      confirmButtonColor: "#6d8bff",
      title: `Merge "${name}" into…`,
      input: "select",
      inputOptions: Object.fromEntries(targets.map((t) => [t.id, t.name])),
      showCancelButton: true,
      confirmButtonText: "Merge",
    });
    if (!res.isConfirmed) return;
    try {
      await post(`/authors/${id}/merge`, { into_id: Number(res.value) });
      load();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const unassign = async (entityId: number, bookId: number) => {
    try {
      await del(`/${kind}/${entityId}/books/${bookId}`);
      load();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const toggle = (name: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });

  const plural = label.endsWith("y") ? `${label.slice(0, -1)}ies` : `${label}s`;

  return (
    <main className="page">
      <h2 className="page-title">{plural}</h2>

      <div className="toolbar">
        <input
          className="search"
          placeholder={`New ${label.toLowerCase()} name`}
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && create()}
        />
        <button className="btn primary" onClick={create}>
          Add {label.toLowerCase()}
        </button>
      </div>

      {loading && <p className="hint">Loading…</p>}
      {error && <p className="error-text">{error}</p>}
      {!loading && !error && groups.length === 0 && (
        <p className="hint">
          Nothing yet. Sync your library, or add one with the field above.
        </p>
      )}

      {groups.map((g) => (
        <section key={g.name}>
          <div className="entity-head">
            <h2
              className="folder-heading group-heading entity-heading"
              onClick={() => toggle(g.name)}
            >
              <span className="group-caret">
                {expanded.has(g.name) ? "▾" : "▸"}
              </span>
              <span
                className={g.id === null ? "crumb-part" : "crumb-leaf"}
              >
                {g.name}
              </span>
              <span className="folder-count">{g.count}</span>
            </h2>
            {g.id !== null && (
              <div className="entity-actions">
                <button className="btn small" onClick={() => rename(g.id!, g.name)}>
                  Rename
                </button>
                {kind === "authors" && (
                  <button className="btn small" onClick={() => merge(g.id!, g.name)}>
                    Merge
                  </button>
                )}
                <button
                  className="btn small danger"
                  onClick={() => remove(g.id!, g.name)}
                >
                  Delete
                </button>
              </div>
            )}
          </div>
          {expanded.has(g.name) && (
            <div className="grid">
              {g.books.map((b) => (
                <div key={b.id} className="managed-card">
                  <BookCard book={b} onEdit={setEditing} />
                  {g.id !== null && (
                    <button
                      className="btn small unassign"
                      onClick={() => unassign(g.id!, b.id)}
                    >
                      Remove from {label.toLowerCase()}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      ))}

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
