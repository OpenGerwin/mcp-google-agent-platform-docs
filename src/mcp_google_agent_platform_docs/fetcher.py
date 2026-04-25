"""Page fetcher: downloads single documentation pages and converts to Markdown.

Adapts the parsing logic from the existing scraper (scrape_docs.py) 
for single-page on-demand fetching.
"""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from . import config
from .source import Source

logger = logging.getLogger(__name__)


class PageFetcher:
    """Fetches and converts single documentation pages to Markdown."""

    def __init__(self, source: Source):
        self.source = source
        self.base_url = source.base_url

    async def fetch_page(self, path: str) -> str | None:
        """Fetch a single page by path, convert HTML → Markdown.

        Args:
            path: Relative path (e.g. "models/gemini/3-1-pro",
                  "scale/memory-bank/setup").

        Returns:
            Markdown content string, or None if fetch failed.
        """
        path = path.strip("/")
        url = f"{self.base_url}/{path}"

        logger.info("Fetching: %s", url)

        try:
            async with httpx.AsyncClient(
                timeout=config.HTTP_TIMEOUT,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; MCP-Docs-Server/0.1; "
                        "+https://github.com/rrromochka/mcp-google-agent-platform-docs)"
                    )
                },
            ) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.warning(
                        "HTTP %d for %s", response.status_code, url
                    )
                    return None

                return self._html_to_markdown(response.text, url)

        except httpx.TimeoutException:
            logger.error("Timeout fetching %s", url)
            return None
        except httpx.HTTPError as e:
            logger.error("HTTP error fetching %s: %s", url, e)
            return None

    def _html_to_markdown(self, html: str, url: str) -> str:
        """Convert HTML page to clean Markdown.

        Extracts the main content area and strips navigation/boilerplate.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Extract page title
        title = ""
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)
        elif soup.title:
            title = soup.title.get_text(strip=True)

        # Find main content area (Google Cloud docs structure)
        content_area = (
            soup.find("article")
            or soup.find("div", class_="devsite-article-body")
            or soup.find("div", attrs={"role": "main"})
            or soup.find("main")
        )

        if not content_area:
            logger.warning("No content area found for %s", url)
            content_area = soup.body or soup

        # Remove unwanted elements
        for selector in [
            "nav",
            "header",
            "footer",
            "script",
            "style",
            "noscript",
            ".devsite-banner",
            ".devsite-nav",
            ".devsite-header",
            ".devsite-footer",
            ".devsite-toc",
            ".devsite-breadcrumb-list",
            ".devsite-feedback",
            '[role="navigation"]',
            '[role="banner"]',
            '[aria-hidden="true"]',
        ]:
            for element in content_area.select(selector):
                element.decompose()

        # Convert to markdown
        markdown_content = md(
            str(content_area),
            heading_style="ATX",
            bullets="-",
            strip=["img"],
        )

        # Clean up the markdown
        markdown_content = self._clean_markdown(markdown_content)

        # Build final document
        header = f"# {title}\n\n" if title else ""
        source_line = f"> Source: {url}\n\n"

        return f"{header}{source_line}{markdown_content}"

    def _clean_markdown(self, text: str) -> str:
        """Clean up markdown artifacts."""
        # Remove excessive blank lines (more than 2 consecutive)
        text = re.sub(r"\n{4,}", "\n\n\n", text)

        # Remove lines that are just whitespace
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            if line.strip() or (cleaned_lines and cleaned_lines[-1].strip()):
                cleaned_lines.append(line.rstrip())

        text = "\n".join(cleaned_lines)

        # Remove trailing whitespace
        text = text.strip()

        return text
