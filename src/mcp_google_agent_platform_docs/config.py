"""Global configuration for the MCP server.

All values can be overridden via environment variables.
"""

import os
from pathlib import Path

# Cache directory for downloaded pages and structure index
CACHE_DIR = os.environ.get(
    "MCP_DOCS_CACHE_DIR",
    str(Path.home() / ".cache" / "mcp-google-agent-platform-docs"),
)

# Time-to-live for cached page content (hours)
CONTENT_TTL_HOURS = int(os.environ.get("MCP_DOCS_CONTENT_TTL", "72"))

# Time-to-live for structure discovery (days)
STRUCTURE_TTL_DAYS = int(os.environ.get("MCP_DOCS_STRUCTURE_TTL", "7"))

# Path to source YAML configurations
SOURCES_DIR = Path(__file__).parent.parent.parent / "sources"

# Default source when user doesn't specify one
DEFAULT_SOURCE = os.environ.get("MCP_DOCS_DEFAULT_SOURCE", "geap")

# HTTP request timeout (seconds)
HTTP_TIMEOUT = int(os.environ.get("MCP_DOCS_HTTP_TIMEOUT", "30"))

# Maximum number of concurrent HTTP requests
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MCP_DOCS_MAX_CONCURRENT", "5"))
