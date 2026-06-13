import { useEffect, useRef, useState } from "react";
import { get, post } from "../api/client";
import type { SyncStatus } from "../types";

export default function SyncPanel({
  onSyncFinished,
}: {
  onSyncFinished: () => void;
}) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [showErrors, setShowErrors] = useState(false);
  const timer = useRef<number | null>(null);
  const wasRunning = useRef(false);

  const poll = async () => {
    try {
      const s = await get<SyncStatus>("/sync/status");
      setStatus(s);
      if (timer.current) window.clearTimeout(timer.current);
      if (s.running) {
        wasRunning.current = true;
        timer.current = window.setTimeout(poll, 600);
      } else if (wasRunning.current) {
        wasRunning.current = false;
        onSyncFinished();
      }
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    poll();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startSync = async () => {
    setError(null);
    try {
      await post("/sync");
      poll();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  useEffect(() => {
    // Reflect any sync already in progress (e.g. started from the first-run
    // guided flow) without the user having to open this panel.
    poll();
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopSync = async () => {
    setError(null);
    try {
      await post("/sync/stop");
      poll();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const running = status?.running ?? false;
  const finished = !!status?.finished_at && !running;

  return (
    <div className="sync-panel">
      <button className="btn primary" onClick={() => setOpen(true)}>
        {running ? "Syncing..." : "Sync"}
      </button>
      {error && !open && <span className="error-text">{error}</span>}

      {open && (
        <div className="modal-backdrop" onMouseDown={() => setOpen(false)}>
          <div className="sync-dialog" onMouseDown={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Sync</h3>
              <button className="icon-btn small" onClick={() => setOpen(false)}>
                x
              </button>
            </div>

            <div className="sync-actions">
              <button className="btn primary" onClick={startSync} disabled={running}>
                Sync now
              </button>
              {running && (
                <button className="btn danger" onClick={stopSync}>
                  {status?.stopping ? "Stopping..." : "Stop sync"}
                </button>
              )}
            </div>

            {error && <p className="error-text">{error}</p>}
            {status && (running || finished || status.stopped) && (
              <>
                <div className="sync-status sync-status-grid">
                  <span>
                    found <b>{status.found}</b>
                  </span>
                  <span>
                    indexed <b>{status.indexed}</b>
                  </span>
                  <span>
                    skipped <b>{status.skipped}</b>
                  </span>
                  <span>
                    deleted <b>{status.deleted}</b>
                  </span>
                  <span className={status.failed ? "error-text" : ""}>
                    failed <b>{status.failed}</b>
                  </span>
                </div>

                {running && (
                  <p className="sync-current" title={status.current_folder}>
                    {status.current_folder}
                    {status.current_file ? ` - ${status.current_file}` : ""}
                  </p>
                )}
                {status.stopped && <p className="hint">Sync stopped.</p>}
                {!running && status.fatal_error && (
                  <p className="error-text">{status.fatal_error}</p>
                )}
                {status.errors.length > 0 && (
                  <button
                    className="btn link"
                    onClick={() => setShowErrors((v) => !v)}
                  >
                    {showErrors ? "hide" : "show"} {status.errors.length} error
                    {status.errors.length > 1 ? "s" : ""}
                  </button>
                )}
              </>
            )}

            {status && showErrors && status.errors.length > 0 && (
              <ul className="sync-errors">
                {status.errors.map((e, i) => (
                  <li key={i}>
                    <code>{e.file_path}</code> - {e.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
