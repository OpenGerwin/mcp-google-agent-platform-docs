"""Wrapper for `mcp dev` which requires absolute imports.

Usage: uv run mcp dev dev_server.py
"""

import sys
from pathlib import Path

# Add src/ to Python path so the package can be imported
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_google_agent_platform_docs.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run(transport="stdio")
