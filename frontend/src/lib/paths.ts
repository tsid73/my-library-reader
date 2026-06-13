// User preference: show absolute file paths in the UI. Off by default so the
// normal UI never exposes machine paths like /mnt/d/Mega/...
const KEY = "showFullPaths";

export function showFullPaths(): boolean {
  return localStorage.getItem(KEY) === "1";
}

export function setShowFullPaths(on: boolean): void {
  localStorage.setItem(KEY, on ? "1" : "0");
}

// Strip the WSL mount prefix (/mnt/d/...) for display when not showing full paths.
export function sanitizePath(path: string): string {
  if (showFullPaths()) return path;
  const norm = path.replace(/\\/g, "/").replace(/^\/+/, "");
  const parts = norm.split("/");
  if (parts.length >= 2 && parts[0] === "mnt" && parts[1].length === 1) {
    return parts.slice(2).join("/");
  }
  return norm;
}
