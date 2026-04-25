"""Cache manager with TTL for documentation pages and structure.

Manages a multi-source cache hierarchy:
    ~/.cache/mcp-google-agent-platform-docs/
    ├── geap/
    │   ├── structure.json   (sitemap discovery results)
    │   └── pages/           (cached markdown files)
    │       ├── models__gemini__3-1-pro.md
    │       └── scale__memory-bank__setup.md
    └── vertex-ai/
        ├── structure.json
        └── pages/
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from . import config
from .source import Source

logger = logging.getLogger(__name__)


@dataclass
class CachedPage:
    """A cached documentation page."""

    path: str
    content: str
    fetched_at: float  # Unix timestamp
    source_id: str


class CacheManager:
    """Multi-source cache with TTL expiration."""

    def __init__(self):
        self.base_dir = Path(config.CACHE_DIR)
        self.content_ttl = config.CONTENT_TTL_HOURS * 3600  # Convert to seconds
        self.structure_ttl = config.STRUCTURE_TTL_DAYS * 86400

    def _source_dir(self, source: Source) -> Path:
        """Get cache directory for a specific source."""
        return self.base_dir / source.id

    def _pages_dir(self, source: Source) -> Path:
        """Get pages cache directory for a source."""
        d = self._source_dir(source) / "pages"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _path_to_filename(self, path: str) -> str:
        """Convert a URL path to a safe filename.

        e.g. "scale/memory-bank/setup" → "scale__memory-bank__setup.md"
        """
        safe = path.strip("/").replace("/", "__")
        if not safe:
            safe = "_index"
        return f"{safe}.md"

    def _filename_to_path(self, filename: str) -> str:
        """Convert a filename back to URL path.

        e.g. "scale__memory-bank__setup.md" → "scale/memory-bank/setup"
        """
        path = filename.removesuffix(".md").replace("__", "/")
        if path == "_index":
            return ""
        return path

    # ── Page cache ──────────────────────────────────────────────

    def get_page(self, source: Source, path: str) -> CachedPage | None:
        """Read a cached page. Returns None if not cached."""
        filename = self._path_to_filename(path)
        filepath = self._pages_dir(source) / filename

        if not filepath.exists():
            return None

        # Read metadata from first line (JSON comment)
        content = filepath.read_text(encoding="utf-8")
        fetched_at = 0.0

        if content.startswith("<!-- META:"):
            first_newline = content.index("\n")
            meta_line = content[9:first_newline].rstrip(" ->").strip()
            try:
                meta = json.loads(meta_line)
                fetched_at = meta.get("fetched_at", 0.0)
            except json.JSONDecodeError:
                pass
            content = content[first_newline + 1 :]

        return CachedPage(
            path=path,
            content=content,
            fetched_at=fetched_at,
            source_id=source.id,
        )

    def is_stale(self, page: CachedPage) -> bool:
        """Check if a cached page has exceeded its TTL."""
        age = time.time() - page.fetched_at
        return age > self.content_ttl

    def save_page(self, source: Source, path: str, content: str) -> None:
        """Save a page to cache with metadata."""
        filename = self._path_to_filename(path)
        filepath = self._pages_dir(source) / filename

        meta = json.dumps({"fetched_at": time.time(), "path": path})
        full_content = f"<!-- META:{meta} -->\n{content}"

        filepath.write_text(full_content, encoding="utf-8")
        logger.debug("Cached: %s/%s", source.id, path)

    def get_all_cached_paths(self, source: Source) -> list[str]:
        """List all cached page paths for a source."""
        pages_dir = self._pages_dir(source)
        paths = []
        for f in pages_dir.glob("*.md"):
            paths.append(self._filename_to_path(f.name))
        return sorted(paths)

    # ── Structure cache ─────────────────────────────────────────

    def get_structure(self, source: Source) -> dict | None:
        """Load cached structure (sitemap discovery results)."""
        filepath = self._source_dir(source) / "structure.json"
        if not filepath.exists():
            return None

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            return None

    def is_structure_stale(self, source: Source) -> bool:
        """Check if structure data is older than TTL."""
        filepath = self._source_dir(source) / "structure.json"
        if not filepath.exists():
            return True

        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            discovered_at = data.get("discovered_at", 0)
            age = time.time() - discovered_at
            return age > self.structure_ttl
        except (json.JSONDecodeError, OSError):
            return True

    def save_structure(self, source: Source, pages: list[str]) -> None:
        """Save structure discovery results."""
        filepath = self._source_dir(source) / "structure.json"
        filepath.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "discovered_at": time.time(),
            "source_id": source.id,
            "page_count": len(pages),
            "pages": sorted(pages),
        }

        filepath.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(
            "Saved structure for %s: %d pages", source.id, len(pages)
        )
