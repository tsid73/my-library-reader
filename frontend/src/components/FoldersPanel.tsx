import { useEffect, useRef, useState } from "react";
import { del, get, post } from "../api/client";
import { confirmAction, toastError, toastOk } from "../lib/alerts";
import { setShowFullPaths, showFullPaths } from "../lib/paths";
import type { RootFolder } from "../types";

export default function FoldersPanel({ onChanged }: { onChanged: () => void }) {
  const [roots, setRoots] = useState<RootFolder[]>([]);
  const [newPath, setNewPath] = useState("");
  const [ruleInputs, setRuleInputs] = useState<
    Record<number, { kind: string; subpath: string }>
  >({});
  const [error, setError] = useState<string | null>(null);
  const [fullPaths, setFullPaths] = useState(showFullPaths());
  const importRef = useRef<HTMLInputElement>(null);

  const load = () =>
    get<RootFolder[]>("/roots").then(setRoots).catch((e) =>
      setError((e as Error).message)
    );

  useEffect(() => {
    load();
  }, []);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const addRoot = async () => {
    const path = newPath.trim();
    if (!path) return;
    const wasEmpty = roots.length === 0;
    setError(null);
    try {
      await post("/roots", { path });
      setNewPath("");
      await load();
      onChanged();
      // Guided first run: offer to scan immediately after the first folder.
      if (wasEmpty) {
        if (await confirmAction("Folder added", "Scan it for books now?", "Scan now")) {
          await post("/sync");
          toastOk("Scanning started — watch the Sync button for progress.");
          onChanged();
        }
      }
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const rescan = (id: number) =>
    run(() => post(`/roots/${id}/rescan`)).then(() => toastOk("Rescan started."));

  const exportData = async () => {
    try {
      const data = await get<unknown>("/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `my-library-backup-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toastError((e as Error).message);
    }
  };

  const importData = async (file: File) => {
    try {
      const payload = JSON.parse(await file.text());
      const res = await post<{ matched: number; skipped: number }>(
        "/import",
        payload
      );
      toastOk(`Imported: ${res.matched} matched, ${res.skipped} skipped.`);
      onChanged();
    } catch (e) {
      toastError(
        e instanceof SyntaxError ? "That file is not valid backup JSON." : (e as Error).message
      );
    }
  };

  const pathText = (r: RootFolder) =>
    (fullPaths ? r.path : r.display_path || r.path) + (r.exists ? "" : " (not found)");

  return (
    <div className="folders-panel">
      <h3>Managed folders</h3>
      {error && <p className="error-text">{error}</p>}
      <ul className="roots-list">
        {roots.map((r) => (
          <li key={r.id}>
            <div className="root-row">
              <code className={r.exists ? "" : "error-text"} title={fullPaths ? r.path : undefined}>
                {pathText(r)}
              </code>
              <div className="root-buttons">
                <button
                  className="btn small"
                  onClick={() => rescan(r.id)}
                  title="Rescan this folder only"
                >
                  Rescan
                </button>
                <button
                  className="btn small danger"
                  onClick={async () => {
                    if (
                      await confirmAction(
                        "Remove folder?",
                        `Remove ${r.display_path || r.path} and all its indexed books, progress, and bookmarks?`,
                        "Remove"
                      )
                    ) {
                      run(() => del(`/roots/${r.id}`));
                    }
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
            <ul className="rules-list">
              {r.rules.map((rule) => (
                <li key={rule.id}>
                  <span className={`rule-kind ${rule.kind}`}>{rule.kind}</span>{" "}
                  <code>{rule.subpath}</code>
                  <button
                    className="btn small"
                    onClick={() => run(() => del(`/rules/${rule.id}`))}
                  >
                    x
                  </button>
                </li>
              ))}
              <li className="rule-add">
                <select
                  value={ruleInputs[r.id]?.kind ?? "exclude"}
                  onChange={(e) =>
                    setRuleInputs({
                      ...ruleInputs,
                      [r.id]: {
                        kind: e.target.value,
                        subpath: ruleInputs[r.id]?.subpath ?? "",
                      },
                    })
                  }
                >
                  <option value="exclude">exclude</option>
                  <option value="include">include</option>
                </select>
                <input
                  placeholder="subfolder path, e.g. Study/Old"
                  value={ruleInputs[r.id]?.subpath ?? ""}
                  onChange={(e) =>
                    setRuleInputs({
                      ...ruleInputs,
                      [r.id]: {
                        kind: ruleInputs[r.id]?.kind ?? "exclude",
                        subpath: e.target.value,
                      },
                    })
                  }
                />
                <button
                  className="btn small"
                  onClick={() =>
                    run(() =>
                      post(`/roots/${r.id}/rules`, {
                        kind: ruleInputs[r.id]?.kind ?? "exclude",
                        subpath: ruleInputs[r.id]?.subpath ?? "",
                      })
                    )
                  }
                >
                  Add rule
                </button>
              </li>
            </ul>
          </li>
        ))}
      </ul>
      <div className="root-add">
        <input
          placeholder="D:\\Books or /mnt/d/Books"
          value={newPath}
          onChange={(e) => setNewPath(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && newPath.trim()) addRoot();
          }}
        />
        <button className="btn" onClick={addRoot}>
          Add folder
        </button>
      </div>
      <p className="hint">
        Paste the folder where your books live. Windows drive paths are accepted.
      </p>

      <div className="folders-footer">
        <label className="inline-check">
          <input
            type="checkbox"
            checked={fullPaths}
            onChange={(e) => {
              setShowFullPaths(e.target.checked);
              setFullPaths(e.target.checked);
            }}
          />
          Show full file paths
        </label>
        <span className="spacer" />
        <button className="btn small" onClick={exportData}>
          Export backup
        </button>
        <button className="btn small" onClick={() => importRef.current?.click()}>
          Import backup
        </button>
        <input
          ref={importRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) importData(f);
            e.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
