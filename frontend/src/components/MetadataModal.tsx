import { useEffect, useRef, useState } from "react";
import { del, get, patch, put } from "../api/client";
import { toastError } from "../lib/alerts";
import { sanitizePath } from "../lib/paths";
import type { BookDetail, Entity } from "../types";

function TagInput({
  label,
  tags,
  onChange,
  placeholder,
}: {
  label: string;
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder: string;
}) {
  const [text, setText] = useState("");
  const add = () => {
    const v = text.trim();
    if (v && !tags.some((t) => t.toLowerCase() === v.toLowerCase())) {
      onChange([...tags, v]);
    }
    setText("");
  };
  return (
    <label className="field">
      <span>{label}</span>
      <div className="tag-input">
        {tags.map((t) => (
          <span className="tag-chip" key={t}>
            {t}
            <button
              type="button"
              onClick={() => onChange(tags.filter((x) => x !== t))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          value={text}
          placeholder={tags.length ? "" : placeholder}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === ",") {
              e.preventDefault();
              add();
            } else if (e.key === "Backspace" && !text && tags.length) {
              onChange(tags.slice(0, -1));
            }
          }}
          onBlur={add}
        />
      </div>
    </label>
  );
}

export default function MetadataModal({
  bookId,
  onClose,
  onSaved,
}: {
  bookId: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [detail, setDetail] = useState<BookDetail | null>(null);
  const [title, setTitle] = useState("");
  const [series, setSeries] = useState("");
  const [authors, setAuthors] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [coverBust, setCoverBust] = useState(Date.now());
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () =>
    get<BookDetail>(`/books/${bookId}`)
      .then((d) => {
        setDetail(d);
        setTitle(d.edited_title ?? d.cleaned_title);
        setSeries(d.edited_series ?? "");
        setAuthors((d.authors as Entity[]).map((a) => a.name));
        setCategories((d.categories as Entity[]).map((c) => c.name));
      })
      .catch((e) => toastError((e as Error).message));

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookId]);

  const save = async () => {
    setSaving(true);
    try {
      await patch(`/books/${bookId}`, {
        edited_title: title.trim() || null,
        edited_series: series.trim() || null,
      });
      await put(`/books/${bookId}/authors`, { names: authors });
      await put(`/books/${bookId}/categories`, { names: categories });
      onSaved();
      onClose();
    } catch (e) {
      toastError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const uploadCover = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`/api/books/${bookId}/cover`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Upload failed (${res.status})`);
      }
      setCoverBust(Date.now());
      onSaved();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const resetCover = async () => {
    try {
      await del(`/books/${bookId}/cover`);
      setCoverBust(Date.now());
      onSaved();
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Edit details</h3>
        {detail && (
          <p className="modal-path" title={sanitizePath(detail.abs_path)}>
            {detail.filename}
          </p>
        )}

        <div className="metadata-body">
          <div className="cover-edit">
            <img
              className="cover-thumb"
              src={`/api/books/${bookId}/cover?t=${coverBust}`}
              alt=""
              onError={(e) => {
                (e.target as HTMLImageElement).style.visibility = "hidden";
              }}
            />
            <button className="btn small" onClick={() => fileRef.current?.click()}>
              Change cover
            </button>
            <button className="btn small" onClick={resetCover}>
              Reset
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadCover(f);
                e.target.value = "";
              }}
            />
          </div>

          <div className="metadata-fields">
            <label className="field">
              <span>Title</span>
              <input value={title} onChange={(e) => setTitle(e.target.value)} />
              {detail && (
                <div className="title-sources">
                  <span className="title-source-label">Use:</span>
                  <button
                    type="button"
                    className="btn small"
                    title={detail.cleaned_title}
                    onClick={() => setTitle(detail.cleaned_title)}
                  >
                    File name
                  </button>
                  {detail.meta_title &&
                    detail.meta_title !== detail.cleaned_title && (
                      <button
                        type="button"
                        className="btn small"
                        title={detail.meta_title}
                        onClick={() => setTitle(detail.meta_title!)}
                      >
                        Metadata
                      </button>
                    )}
                </div>
              )}
            </label>
            <label className="field">
              <span>Series</span>
              <input value={series} onChange={(e) => setSeries(e.target.value)} />
            </label>
            <TagInput
              label="Authors"
              tags={authors}
              onChange={setAuthors}
              placeholder="Type a name, press Enter"
            />
            <TagInput
              label="Categories"
              tags={categories}
              onChange={setCategories}
              placeholder="Type a category, press Enter"
            />
          </div>
        </div>

        <div className="modal-actions">
          <span className="spacer" />
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <button className="btn primary" onClick={save} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
