import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines) so we avoid an extra dependency.
    Existing environment variables always win."""
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()
DATA_DIR = Path(os.environ.get("LIBRARY_DATA_DIR", BASE_DIR / "data"))
COVERS_DIR = DATA_DIR / "covers"
DB_PATH = DATA_DIR / "library.db"

# The folder preconfigured on first run. Override with the LIBRARY_ROOT env var
# (or a .env file). Empty by default for a clean public checkout — users add
# roots from the Folders panel. Example: LIBRARY_ROOT=/mnt/d/Books
DEFAULT_ROOT = os.environ.get("LIBRARY_ROOT", "").strip()

# .htm is treated as html
SUPPORTED_EXTENSIONS = {".epub", ".pdf", ".txt", ".html", ".htm"}
IGNORED_EXTENSIONS = {".mobi", ".azw3"}

# FUTURE: audiobook / media support. When added, extend SUPPORTED_EXTENSIONS
# with audio formats (e.g. .mp3, .m4b, .m4a, .opus) and add a media-player
# reader on the frontend plus a `duration`/`media` column on Book.
# Multiple root folders are ALREADY supported (see root_folders table + the
# Folders panel); only the initial DEFAULT_ROOT below is a single seed.
FUTURE_AUDIO_EXTENSIONS = {".mp3", ".m4b", ".m4a", ".opus"}

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8011"))
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"
FRONTEND_URL = "http://localhost:5173"

# Single-server mode: when set, the backend serves the built SPA itself (one
# port). The `npm start` launcher sets this; `npm run dev` does not (Vite serves
# the SPA with hot reload instead).
SERVE_SPA = os.environ.get("MLR_SERVE_SPA") == "1"

COVER_MAX_WIDTH = 400
COVER_JPEG_QUALITY = 80


def ensure_dirs() -> None:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)


def format_for_extension(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return "html" if ext == "htm" else ext
