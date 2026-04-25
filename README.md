# mcp-google-agent-platform-docs

MCP server providing Google AI platform documentation to AI agents.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-1.27.0-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> Part of [OpenGerwin MCP Servers](https://github.com/OpenGerwin/mcp)

## What is this?

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that gives AI agents direct access to Google's AI platform documentation — both the current **Gemini Enterprise Agent Platform (GEAP)** and the legacy **Vertex AI Generative AI** docs.

Instead of hallucinating API details, your AI assistant can look up the actual documentation in real-time.

## Features

- 🔍 **Full-text search** across 3400+ documentation pages
- 📄 **On-demand fetching** — pages are downloaded and cached as you need them
- 🗂️ **Dual source** — current GEAP + legacy Vertex AI documentation
- ⚡ **Smart caching** — 72-hour TTL, stale fallback on network errors
- 🗺️ **Auto-discovery** — new pages found via sitemap scanning (weekly)
- 🧩 **Plug & play** — works with Claude Desktop, Cursor, VS Code, any MCP client

## Quick Start

### Install

```bash
# Using pip
pip install mcp-google-agent-platform-docs

# Using uv (recommended)
uv pip install mcp-google-agent-platform-docs
```

### Configure Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-ai-docs": {
      "command": "mcp-google-agent-platform-docs"
    }
  }
}
```

### Configure Cursor / VS Code

Add to your MCP settings:

```json
{
  "mcpServers": {
    "google-ai-docs": {
      "command": "mcp-google-agent-platform-docs",
      "transport": "stdio"
    }
  }
}
```

## Tools

### `search_docs`
Search documentation by keywords.

```
search_docs("Memory Bank setup", source="geap")
search_docs("function calling", source="vertex-ai")
```

### `get_doc`
Get full content of a specific page.

```
get_doc("scale/memory-bank/setup", source="geap")
get_doc("multimodal/function-calling", source="vertex-ai")
```

### `list_sections`
Browse documentation structure.

```
list_sections(source="geap")
```

### `list_models`
Quick reference for all available AI models (Gemini, Imagen, Veo, Claude, etc.).

```
list_models()
```

## Documentation Sources

| Source ID | Platform | Pages | Status |
|---|---|---|---|
| `geap` | Gemini Enterprise Agent Platform | 2300+ | **Primary** (current) |
| `vertex-ai` | Vertex AI Generative AI | 1100+ | Legacy (archive) |

### GEAP Sections
- **Agent Studio** — Visual agent builder
- **Agents → Build** — Runtime, ADK, Agent Garden, RAG Engine
- **Agents → Scale** — Sessions, Memory Bank, Code Execution
- **Agents → Govern** — Policies, Agent Gateway, Model Armor
- **Agents → Optimize** — Observability, Evaluation, Quality Alerts
- **Models** — Gemini, Imagen, Veo, Lyria, Partners, Open Models
- **Notebooks** — Jupyter tutorials

## Configuration

Environment variables for customization:

| Variable | Default | Description |
|---|---|---|
| `MCP_DOCS_CACHE_DIR` | `~/.cache/mcp-google-agent-platform-docs` | Cache directory |
| `MCP_DOCS_CONTENT_TTL` | `72` | Page cache TTL (hours) |
| `MCP_DOCS_STRUCTURE_TTL` | `7` | Structure cache TTL (days) |
| `MCP_DOCS_DEFAULT_SOURCE` | `geap` | Default documentation source |
| `MCP_DOCS_HTTP_TIMEOUT` | `30` | HTTP timeout (seconds) |

## Development

```bash
# Clone
git clone https://github.com/OpenGerwin/mcp-google-agent-platform-docs.git
cd mcp-google-agent-platform-docs

# Install dependencies
uv sync

# Run server locally
uv run mcp-google-agent-platform-docs

# Test with MCP Inspector
uv run mcp dev src/mcp_google_agent_platform_docs/server.py
```

## Architecture

```
mcp-google-agent-platform-docs/
├── sources/                    # YAML source configurations
│   ├── geap.yaml               # GEAP (primary)
│   └── vertex-ai.yaml          # Vertex AI (legacy)
├── src/mcp_google_agent_platform_docs/
│   ├── server.py               # FastMCP server + 4 tools
│   ├── source.py               # Source model (YAML loader)
│   ├── fetcher.py              # HTML → Markdown converter
│   ├── cache.py                # TTL cache manager
│   ├── discovery.py            # Sitemap-based page discovery
│   ├── search.py               # TF-IDF search engine
│   └── config.py               # Global configuration
└── tests/
```

## License

MIT — see [LICENSE](LICENSE).

---

> Part of [OpenGerwin MCP Servers](https://github.com/OpenGerwin/mcp)
