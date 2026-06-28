import { useCallback, useEffect, useState } from "react";
import { get } from "../api/client";
import BookCard from "../components/BookCard";
import FoldersPanel from "../components/FoldersPanel";
import MetadataModal from "../components/MetadataModal";
import SyncPanel from "../components/SyncPanel";
import type {
  BookCard as BookCardT,
  FilterOptions,
  LibraryResponse,
  RootFolder,
} from "../types";

export default function LibraryPage() {
  const [library, setLibrary] = useState<LibraryResponse | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(
    null
  );
  const [filters, setFilters] = useState<{ format: string; folders: string[]; author: string; category: string }>(() => {
    const defaults = { format: "", folders: [], author: "", category: "" };
    try {
      const parsed = JSON.parse(localStorage.getItem("library.filters") || "");
      return { ...defaults, ...(parsed || {}) };
    } catch {
      return defaults;
    }
  });
  const [sort, setSort] = useState<"title" | "recent">(
    () => (localStorage.getItem("library.sort") as "title" | "recent") || "title"
  );
  
  useEffect(() => localStorage.setItem("library.filters", JSON.stringify(filters)), [filters]);
  useEffect(() => localStorage.setItem("library.sort", sort), [sort]);

  const [offset, setOffset] = useState(0);
  const LIMIT = 50;
  const [searchInput, setSearchInput] = useState("");
  const [searchResults, setSearchResults] = useState<BookCardT[] | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [libraryError, setLibraryError] = useState<string | null>(null);
  const [editing, setEditing] = useState<BookCardT | null>(null);
  const [showFolders, setShowFolders] = useState(false);
  const [roots, setRoots] = useState<RootFolder[] | null>(null);
  const [folderSearch, setFolderSearch] = useState("");

  const loadRoots = useCallback(() => {
    get<RootFolder[]>("/roots")
      .then((r) => {
        setRoots(r);
        // First run (no library folder configured): open the Folders panel so
        // the user can add one. The app never requires a path to start.
        if (r.length === 0) setShowFolders(true);
      })
      .catch(() => setRoots([]));
  }, []);

  const loadLibrary = useCallback((append = false) => {
    const params = new URLSearchParams();
    if (filters.format) params.set("format", filters.format);
    filters.folders.forEach((folder) => params.append("folder", folder));
    if (filters.author) params.set("author", filters.author);
    if (filters.category) params.set("category", filters.category);
    params.set("sort", sort);
    params.set("limit", String(LIMIT));
    params.set("offset", String(append ? offset : 0));
    setLibraryError(null);
    get<LibraryResponse>(`/library?${params}`)
      .then((res) => {
        if (append) {
          setLibrary((prev) => {
            if (!prev) return res;
            const newSections = [...prev.sections];
            for (const sec of res.sections) {
              const existing = newSections.find((s) => s.folder === sec.folder);
              if (existing) {
                existing.books = [...existing.books, ...sec.books];
              } else {
                newSections.push(sec);
              }
            }
            return { sections: newSections, total: res.total };
          });
        } else {
          setLibrary(res);
        }
      })
      .catch((e) => setLibraryError((e as Error).message));
    get<FilterOptions>("/library/filters")
      .then(setFilterOptions)
      .catch(() => {});
  }, [filters, sort, offset]);

  useEffect(() => {
    loadLibrary(offset > 0);
  }, [loadLibrary, offset]);

  useEffect(() => {
    loadRoots();
  }, [loadRoots]);

  const runSearch = async () => {
    const q = searchInput.trim();
    setSearchError(null);
    if (!q) {
      setSearchResults(null);
      return;
    }
    try {
      const res = await get<{ books: BookCardT[] }>(
        `/search?q=${encodeURIComponent(q)}`
      );
      setSearchResults(res.books);
    } catch (e) {
      setSearchError((e as Error).message);
    }
  };

  const refresh = () => {
    loadLibrary();
    loadRoots();
    if (searchResults !== null) runSearch();
  };

  // FUTURE: the Author filter will become a searchable/typeahead dropdown
  // (e.g. react-select) so large author lists are easy to navigate. For now
  // it is a plain <select>, kept visually consistent with the other filters.
  const select = (
    label: string,
    key: "format" | "author" | "category",
    options: string[]
  ) => (
    <select
      className="filter-select"
      value={filters[key]}
      onChange={(e) => {
        setFilters({ ...filters, [key]: e.target.value });
        setOffset(0);
      }}
      title={label}
    >
      <option value="">{label}: all</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );

  const selectedFolderOptions =
    filterOptions?.folders.filter((f) => filters.folders.includes(f.value)) ?? [];
  const folderMatches =
    filterOptions?.folders
      .filter(
        (f) =>
          !filters.folders.includes(f.value) &&
          f.label.toLowerCase().includes(folderSearch.trim().toLowerCase())
      )
      .slice(0, 8) ?? [];
  const addFolder = (value: string) => {
    if (!value) return;
    setFilters((current) => ({
      ...current,
      folders: current.folders.includes(value)
        ? current.folders
        : [...current.folders, value],
    }));
    setOffset(0);
    setFolderSearch("");
  };
  const removeFolder = (value: string) => {
    setFilters((current) => ({
      ...current,
      folders: current.folders.filter((f) => f !== value),
    }));
    setOffset(0);
  };

  return (
    <main className="page">
      <div className="toolbar">
        <SyncPanel onSyncFinished={refresh} />
        <input
          className="search"
          placeholder="Search (press Enter)…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") runSearch();
          }}
        />
        {searchResults !== null && (
          <button
            className="btn"
            onClick={() => {
              setSearchResults(null);
              setSearchInput("");
              setSearchError(null);
            }}
          >
            Clear search
          </button>
        )}
        <button className="btn" onClick={() => setShowFolders((v) => !v)}>
          Manage folders
        </button>
      </div>

      {showFolders && <FoldersPanel onChanged={refresh} />}

      <div className="toolbar filters">
        {filterOptions && (
          <>
            {select("Format", "format", filterOptions.formats)}
            <div className="folder-filter">
              <input
                className="filter-folder-input"
                placeholder="Search folders"
                value={folderSearch}
                onChange={(e) => setFolderSearch(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && folderMatches[0]) {
                    e.preventDefault();
                    addFolder(folderMatches[0].value);
                  }
                }}
              />
              {folderSearch.trim() && folderMatches.length > 0 && (
                <div className="folder-filter-menu">
                  {folderMatches.map((folder) => (
                    <button
                      key={folder.value}
                      type="button"
                      onClick={() => addFolder(folder.value)}
                    >
                      {folder.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {select("Author", "author", filterOptions.authors)}
            {select("Category", "category", filterOptions.categories)}
          </>
        )}
        <select
          value={sort}
          onChange={(e) => {
            setSort(e.target.value as "title" | "recent");
            setOffset(0);
          }}
          title="Sort"
        >
          <option value="title">Sort: title</option>
          <option value="recent">Sort: recently opened</option>
        </select>
      </div>

      {selectedFolderOptions.length > 0 && (
        <div className="filter-chips">
          {selectedFolderOptions.map((folder) => (
            <button
              key={folder.value}
              className="filter-chip"
              onClick={() => removeFolder(folder.value)}
              title="Remove folder filter"
            >
              {folder.label} x
            </button>
          ))}
        </div>
      )}

      {searchError && <p className="error-text">Search failed: {searchError}</p>}
      {libraryError && (
        <p className="error-text">Could not load library: {libraryError}</p>
      )}

      {searchResults !== null ? (
        <section>
          <h2 className="folder-heading">
            Search results ({searchResults.length})
          </h2>
          {searchResults.length === 0 && <p className="hint">No books match.</p>}
          <div className="grid">
            {searchResults.map((b) => (
              <BookCard key={b.id} book={b} onEdit={setEditing} />
            ))}
          </div>
        </section>
      ) : (
        <>
          {roots !== null && roots.length === 0 && (
            <div className="welcome-card">
              <h2>👋 Welcome to your library</h2>
              <p>
                Add the folder where your books live to get started. Your files
                are indexed in place — nothing is copied, moved, or changed.
              </p>
              <p className="hint">
                Use <b>Manage folders</b>. You can paste a Windows path like
                <code>D:\Books</code> or a WSL path like
                <code>/mnt/d/Books</code>.
              </p>
              <button className="btn primary" onClick={() => setShowFolders(true)}>
                Add a books folder
              </button>
            </div>
          )}
          {roots !== null && roots.length > 0 && library?.total === 0 && (
            <p className="hint">
              No books indexed yet in your folder(s). Press <b>Sync</b> to
              scan them.
            </p>
          )}
          {library?.sections.map((section) => (
            <section key={section.folder}>
              <h2 className="folder-heading" title={section.crumbs.join(" / ")}>
                {section.crumbs.map((part, i) => (
                  <span key={i} className="crumb">
                    {i > 0 && <span className="crumb-sep">›</span>}
                    <span
                      className={
                        i === section.crumbs.length - 1
                          ? "crumb-leaf"
                          : "crumb-part"
                      }
                    >
                      {part}
                    </span>
                  </span>
                ))}
                <span className="folder-count">{section.books.length}</span>
              </h2>
              <div className="grid">
                {section.books.map((b) => (
                  <BookCard key={b.id} book={b} onEdit={setEditing} />
                ))}
              </div>
            </section>
          ))}
          {library && library.total > library.sections.reduce((acc, sec) => acc + sec.books.length, 0) && (
            <div style={{ textAlign: "center", margin: "2rem 0" }}>
              <button className="btn" onClick={() => setOffset((o) => o + LIMIT)}>
                Load more books
              </button>
            </div>
          )}
        </>
      )}

      {editing && (
        <MetadataModal
          bookId={editing.id}
          onClose={() => setEditing(null)}
          onSaved={refresh}
        />
      )}
    </main>
  );
}
