"""MCP Server: Google Agent Platform Documentation.

Provides AI agents with access to Google AI platform documentation
via the Model Context Protocol (MCP).

Sources:
  - GEAP (Gemini Enterprise Agent Platform) — current platform
  - Vertex AI Generative AI — legacy archive

Tools:
  - search_docs: Full-text search across documentation
  - get_doc: Retrieve a specific page by path
  - list_sections: Browse documentation structure
  - list_models: Quick reference for available AI models
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import config
from .cache import CacheManager
from .discovery import StructureDiscovery
from .fetcher import PageFetcher
from .search import SearchEngine
from .source import Source, load_sources

# ── Logging ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Server Setup ────────────────────────────────────────────────

mcp = FastMCP(
    "google-agent-platform-docs",
    instructions=(
        "Provides access to Google AI platform documentation. "
        "Use search_docs to find information, get_doc to read full pages, "
        "list_sections to browse the structure, and list_models for a model reference. "
        "Default source is 'geap' (Gemini Enterprise Agent Platform). "
        "Use source='vertex-ai' for legacy Vertex AI documentation."
    ),
)

# ── Global State ────────────────────────────────────────────────

_sources: dict[str, Source] = {}
_cache = CacheManager()
_search = SearchEngine()
_initialized = False
_init_lock = asyncio.Lock()


async def _ensure_initialized() -> None:
    """Lazy initialization: load sources, discover structure, build index."""
    global _sources, _initialized

    async with _init_lock:
        if _initialized:
            return

        logger.info("Initializing MCP server...")

        # Load source configurations
        _sources = load_sources()
        if not _sources:
            logger.error("No sources found! Check sources/ directory.")
            _initialized = True
            return

        logger.info("Loaded %d sources: %s", len(_sources), list(_sources.keys()))

        # For each source: discover structure and build search index
        for source in _sources.values():
            await _refresh_source(source)

        _initialized = True
        logger.info("✅ Server initialized. %d docs indexed.", _search.doc_count)


async def _refresh_source(source: Source) -> None:
    """Refresh structure and search index for a source."""
    # Check if structure needs refresh
    if _cache.is_structure_stale(source):
        logger.info("Discovering structure for %s...", source.id)
        discovery = StructureDiscovery(source)

        old_structure = _cache.get_structure(source)
        known_pages = old_structure.get("pages", []) if old_structure else None

        result = await discovery.discover(known_pages)

        if result.all_pages:
            _cache.save_structure(source, result.all_pages)

            if result.added:
                logger.info(
                    "  %d new pages discovered for %s",
                    len(result.added), source.id,
                )
            if result.removed:
                logger.info(
                    "  %d pages removed from %s",
                    len(result.removed), source.id,
                )
    else:
        logger.info("Structure for %s is fresh (within TTL).", source.id)

    # Build search index from cached pages
    cached_paths = _cache.get_all_cached_paths(source)
    if cached_paths:
        pages = {}
        for path in cached_paths:
            page = _cache.get_page(source, path)
            if page:
                pages[path] = page.content
        if pages:
            _search.build_index(pages, source.id)
            logger.info(
                "Indexed %d cached pages for %s", len(pages), source.id
            )


def _get_source(source_id: str) -> Source | None:
    """Get a source by ID, defaulting to config.DEFAULT_SOURCE."""
    if source_id in _sources:
        return _sources[source_id]
    logger.warning("Unknown source: %s", source_id)
    return None


async def _get_or_fetch_page(source: Source, path: str) -> str | None:
    """Get a page from cache, or fetch and cache it."""
    # Check cache
    cached = _cache.get_page(source, path)
    if cached and not _cache.is_stale(cached):
        return cached.content

    # Fetch live
    fetcher = PageFetcher(source)
    content = await fetcher.fetch_page(path)

    if content:
        _cache.save_page(source, path, content)
        # Update search index with new content
        _search.build_index({path: content}, source.id)
        return content

    # Fallback to stale cache
    if cached:
        logger.info("Using stale cache for %s/%s", source.id, path)
        return cached.content

    return None


# ── MCP Tools ───────────────────────────────────────────────────


@mcp.tool()
async def search_docs(
    query: str,
    max_results: int = 5,
    source: str = "geap",
) -> str:
    """Search Google AI platform documentation.

    Args:
        query: Search terms (e.g. "function calling", "Memory Bank setup",
               "Agent Development Kit", "Gemini 3.1 Pro")
        max_results: Number of results to return (default: 5, max: 20)
        source: Documentation source:
                - "geap" (default) — Gemini Enterprise Agent Platform (current)
                - "vertex-ai" — Vertex AI Generative AI (legacy)

    Returns:
        Matching documentation pages with titles, paths, and excerpts.
        Use get_doc(path) to read the full content of any result.
    """
    await _ensure_initialized()

    max_results = min(max_results, 20)
    results = _search.search(query, max_results=max_results, source_id=source)

    if not results:
        return f"No results found for '{query}' in source '{source}'."

    lines = [f"## Search results for: {query}\n"]
    lines.append(f"Source: {source} | {len(results)} results\n")

    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.title}")
        lines.append(f"**Path:** `{r.path}`")
        lines.append(f"**Score:** {r.score}")
        lines.append(f"**Excerpt:** {r.excerpt}")
        lines.append("")

    lines.append(
        "💡 Use `get_doc(path)` to read the full content of any page above."
    )

    return "\n".join(lines)


@mcp.tool()
async def get_doc(path: str, source: str = "geap") -> str:
    """Get full content of a specific documentation page.

    Args:
        path: Documentation page path, e.g.:
              GEAP paths:
                - "models/gemini/3-1-pro"
                - "build/runtime/quickstart"
                - "scale/memory-bank/setup"
                - "govern/policies/overview"
                - "optimize/evaluation/agent-evaluation"
                - "agent-studio/overview"
              Vertex AI paths:
                - "multimodal/function-calling"
                - "rag-engine/rag-overview"
                - "models/gemini/2-5-flash"
        source: "geap" (default) or "vertex-ai"

    Returns:
        Complete page content in Markdown format.
        If not cached, fetches live from the documentation site.
    """
    await _ensure_initialized()

    src = _get_source(source)
    if not src:
        available = ", ".join(_sources.keys())
        return f"❌ Unknown source '{source}'. Available: {available}"

    content = await _get_or_fetch_page(src, path)

    if content:
        return content

    return (
        f"❌ Page not found: `{path}` (source: {source})\n\n"
        f"Try using `search_docs()` to find the correct path, "
        f"or `list_sections()` to browse available documentation."
    )


@mcp.tool()
async def list_sections(source: str = "geap") -> str:
    """List all documentation sections and their page counts.

    Args:
        source: "geap" (default) or "vertex-ai"

    Returns:
        Structured overview of all available documentation sections
        with descriptions and page counts.
    """
    await _ensure_initialized()

    src = _get_source(source)
    if not src:
        available = ", ".join(_sources.keys())
        return f"❌ Unknown source '{source}'. Available: {available}"

    # Get structure data
    structure = _cache.get_structure(src)
    all_pages = structure.get("pages", []) if structure else []

    lines = [f"# {src.name}\n"]
    lines.append(f"**Source ID:** `{src.id}`")
    lines.append(f"**Base URL:** {src.base_url}")
    lines.append(f"**Total pages discovered:** {len(all_pages)}\n")

    if not src.sections:
        lines.append("No sections defined.")
        return "\n".join(lines)

    lines.append("## Sections\n")

    for section in src.sections:
        # Count pages belonging to this section
        count = sum(
            1
            for page in all_pages
            if any(
                page.startswith(prefix.lstrip("/"))
                for prefix in section.path_prefixes
                if prefix
            )
        )

        lines.append(f"### {section.name}")
        if section.description:
            lines.append(f"{section.description}")
        lines.append(f"- Pages: **{count}**")
        lines.append(
            f"- Path prefix: `{section.path_prefixes[0] if section.path_prefixes else 'N/A'}`"
        )
        lines.append("")

    lines.append(
        "💡 Use `search_docs(query)` to search within any section, "
        "or `get_doc(path)` to read a specific page."
    )

    return "\n".join(lines)


@mcp.tool()
async def list_models() -> str:
    """List all available AI models on Google's platform.

    Returns a quick reference of all models organized by family:
    Google (Gemini, Imagen, Veo, Lyria), Partners (Claude, Grok, Mistral, Llama),
    and Open Models (DeepSeek, Qwen, Kimi, etc.).
    """
    await _ensure_initialized()

    # This is a curated static reference that's useful even without cache
    return """# Available AI Models

## Google Models

### Gemini (Text & Multimodal)
| Model | Key Features |
|---|---|
| **Gemini 3.1 Pro** | Latest flagship, 1M context |
| **Gemini 3 Pro** | High quality, balanced |
| **Gemini 3 Pro (Image)** | Native image generation |
| **Gemini 2.5 Pro** | Previous gen flagship |
| **Gemini 3.1 Flash (Image)** | Fast image generation |
| **Gemini 3 Flash** | Speed-optimized |
| **Gemini 2.5 Flash** | Previous gen fast |
| **Gemini 2.0 Flash** | Legacy fast model |
| **Gemini 3.1 Flash Lite** | Ultra-efficient |
| **Gemini 2.5 Flash Lite** | Previous gen lite |
| **Gemini Embedding 2** | Text + code embeddings |

### Imagen (Image Generation)
- Imagen 4.0, Imagen 3.0
- Virtual Try-On, Upscale

### Veo (Video Generation)
- Veo 3.1, Veo 3.0, Veo 2.0

### Lyria (Music Generation)
- Lyria 3, Lyria 002

## Partner Models
| Partner | Models |
|---|---|
| **Anthropic** | Claude Opus 4.7, Sonnet 4.6, Opus 4.5, Haiku 4.5 |
| **xAI** | Grok 4.1 Fast, Grok 4-20 |
| **Mistral** | Mistral Medium 3, Small 3.1, OCR, Codestral 2 |
| **Meta** | Llama 4 Maverick, Llama 4 Scout, Llama 3.3 |

## Open Models (Model-as-a-Service)
| Provider | Models |
|---|---|
| **DeepSeek** | V3.2, V3.1, R1-0528, OCR |
| **Qwen** | Qwen3 Next Instruct/Thinking, Coder, 235B |
| **Kimi** | K2 Thinking |
| **MiniMax** | M2 |
| **OpenAI (open)** | GPT-OSS 120B, 20B |
| **Google** | Gemma 4 26B |

💡 Use `get_doc("models/gemini/3-1-pro")` for detailed model documentation.
"""


# ── Entry Point ─────────────────────────────────────────────────


def main():
    """Run the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
