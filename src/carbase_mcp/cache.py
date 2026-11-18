"""On-disk cache shared by all carbase-mcp processes of one user, bounded in MB and age.

Settings (environment): CARBASE_MCP_CACHE_DIR (default $XDG_CACHE_HOME/carbase-mcp or
~/.cache/carbase-mcp), CARBASE_MCP_CACHE_MB (default 100; 0 disables the cache) and
CARBASE_MCP_CACHE_DAYS (default 30; upper bound for every entry).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import stat
import time
from pathlib import Path

log = logging.getLogger(__name__)

DAY = 86_400.0
COOKIE_FILE = "cookies.json"


def ttl_for(url: str) -> float:
    """How long a response stays fresh: specs rarely change, prices and counts do."""
    path, _, query = url.partition("?")
    if path.startswith("/auto/"):
        return 30 * DAY  # one version's specifications
    if query == "format=json" and path.count("/") <= 3:
        return 7 * DAY  # brand list (/carbase/) or a brand's model list (/carbase/{brand}/)
    return DAY  # search results


def _env_number(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        log.warning("Ignoring invalid %s", name)
        return default


class DiskCache:
    def __init__(self, root: Path, max_mb: float = 100, max_days: float = 30) -> None:
        self.root = root
        self.max_bytes = int(max_mb * 1_000_000)
        self.max_age = max_days * DAY
        self._safe: bool | None = None  # root checked on first use

    @classmethod
    def from_env(cls) -> DiskCache | None:
        max_mb = _env_number("CARBASE_MCP_CACHE_MB", 100)
        if not max_mb:
            return None
        base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
        root = Path(os.environ.get("CARBASE_MCP_CACHE_DIR") or Path(base) / "carbase-mcp")
        return cls(root, max_mb, _env_number("CARBASE_MCP_CACHE_DAYS", 30))

    def _root_ok(self) -> bool:
        """Only use a real directory owned by us that nobody else can write to.

        In a shared location (e.g. under /tmp) another user could otherwise plant entries or
        symlinks that make us overwrite files.
        """
        if self._safe is None:
            try:
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                st = os.lstat(self.root)
                mine = not hasattr(os, "getuid") or st.st_uid == os.getuid()
                self._safe = stat.S_ISDIR(st.st_mode) and mine and not st.st_mode & 0o022
            except OSError:
                self._safe = False
            if not self._safe:
                log.warning("Cache disabled: %s is not a private directory of this user", self.root)
        return self._safe

    def _file(self, key: str) -> Path:
        return self.root / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def get(self, key: str, ttl: float) -> str | None:
        if not self._root_ok():
            return None
        path = self._file(key)
        try:
            age = time.time() - path.stat().st_mtime
            if age > min(ttl, self.max_age):
                return None
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or entry.get("key") != key or not isinstance(entry.get("body"), str):
            return None
        return entry["body"]

    def put(self, key: str, body: str) -> None:
        if self._write(self._file(key), {"key": key, "body": body}):
            self._evict()

    def load_cookies(self) -> list[dict]:
        if not self._root_ok():
            return []
        try:
            cookies = json.loads((self.root / COOKIE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return cookies if isinstance(cookies, list) else []

    def save_cookies(self, cookies: list[dict]) -> None:
        self._write(self.root / COOKIE_FILE, cookies)

    def _write(self, path: Path, data: object) -> bool:
        """Atomic write, readable only by the owner. Failures only cost the cache."""
        if not self._root_ok():
            return False
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(tmp, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, path)
            return True
        except OSError as exc:
            log.warning("Cache write failed: %s", exc)
            with contextlib.suppress(OSError):
                tmp.unlink()
            return False

    def _evict(self) -> None:
        """Drop entries older than max_age, then the oldest until the cache fits in max_bytes."""
        now, entries, total = time.time(), [], 0
        with contextlib.suppress(OSError), os.scandir(self.root) as it:
            for e in it:
                if e.name.endswith(".json") and e.name != COOKIE_FILE:
                    st = e.stat()
                    entries.append((st.st_mtime, st.st_size, e.path))
                    total += st.st_size
        for mtime, size, path in sorted(entries):
            if total <= self.max_bytes and now - mtime <= self.max_age:
                break
            with contextlib.suppress(OSError):
                os.unlink(path)
                total -= size
