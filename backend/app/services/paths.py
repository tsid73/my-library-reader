import os
import re


_WINDOWS_DRIVE = re.compile(r"^([a-zA-Z]):[\\/]*(.*)$")


def normalize_root_path(raw: str) -> str:
    path = raw.strip().strip("\"'")
    if not path:
        raise ValueError("Enter a folder path.")

    match = _WINDOWS_DRIVE.match(path)
    if match:
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/").strip("/")
        path = f"/mnt/{drive}" + (f"/{rest}" if rest else "")
    else:
        path = path.replace("\\", "/")

    path = path.rstrip("/") or "/"
    if not os.path.isabs(path):
        raise ValueError("Use a full folder path, for example D:\\Books.")
    if os.path.isfile(path):
        raise ValueError("Use a folder, not a file.")
    if not os.path.isdir(path):
        raise ValueError("That folder does not exist or cannot be opened.")
    return os.path.abspath(path)


def display_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/") if normalized else []
    if len(parts) >= 2 and parts[0] == "mnt" and len(parts[1]) == 1:
        parts = parts[2:]
    return "/".join(parts) or path


def relative_display(path: str, root_paths) -> str:
    """Sanitized path for the UI: relative to the matching root's parent so the
    root's own name is kept (e.g. 'Books/Study/Tech/x.pdf') and the machine
    prefix (/mnt/d/Mega/, home dirs) is dropped. Falls back to display_path."""
    if not path:
        return path
    p = path.replace("\\", "/")
    best = ""
    for r in root_paths or []:
        rp = r.replace("\\", "/").rstrip("/")
        if p == rp or p.startswith(rp + "/"):
            if len(rp) > len(best):
                best = rp
    if best:
        anchor = best.rsplit("/", 1)[0]  # keep the root folder's own name
        rel = p[len(anchor):].lstrip("/") if anchor else p.lstrip("/")
        return rel or display_path(path)
    return display_path(path)
