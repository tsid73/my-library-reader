import hashlib
import os

# Partial hash: SHA-256 over (file size, first 1 MiB, last 1 MiB).
# Full-file hashing over the /mnt/d 9P mount is too slow for large libraries;
# this is sufficient to detect content changes, renames, and duplicates for ebooks.
CHUNK = 1024 * 1024


def partial_hash(path: str) -> str:
    size = os.path.getsize(path)
    h = hashlib.sha256()
    h.update(str(size).encode())
    with open(path, "rb") as f:
        h.update(f.read(CHUNK))
        if size > 2 * CHUNK:
            f.seek(-CHUNK, os.SEEK_END)
            h.update(f.read(CHUNK))
        elif size > CHUNK:
            h.update(f.read())
    return h.hexdigest()
