"""Structure discovery via sitemap.xml.

Scans Google Cloud sitemaps to discover all documentation pages
for a given source, and detects added/removed pages.

Performance notes:
- Sub-sitemaps are fetched concurrently (up to MAX_CONCURRENT_REQUESTS)
- Google Cloud has ~60-180 sub-sitemaps; we scan all since the filenames
  don't indicate content. Results are cached for STRUCTURE_TTL_DAYS.
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from . import config
from .source import Source

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Result of a structure discovery scan."""

    all_pages: list[str]
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


class StructureDiscovery:
    """Discovers documentation pages via sitemap.xml scanning."""

    # Google Cloud sitemaps use this namespace
    SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def __init__(self, source: Source):
        self.source = source

    async def discover(
        self, known_pages: list[str] | None = None
    ) -> DiscoveryResult:
        """Discover all documentation pages for this source.

        1. Fetch the sitemap index
        2. Fetch ALL sub-sitemaps concurrently
        3. Filter URLs matching our source filter
        4. Extract relative paths
        5. Compare with known pages to find added/removed

        Args:
            known_pages: Previously known page paths (for diff).

        Returns:
            DiscoveryResult with all pages and diff info.
        """
        logger.info(
            "Starting structure discovery for %s from %s",
            self.source.id,
            self.source.sitemap_url,
        )

        all_urls = await self._scan_sitemap()

        # Extract relative paths from full URLs
        all_paths = []
        for url in all_urls:
            path = self._url_to_path(url)
            if path is not None:
                all_paths.append(path)

        all_paths = sorted(set(all_paths))
        logger.info(
            "Discovered %d pages for %s", len(all_paths), self.source.id
        )

        # Compute diff
        if known_pages is not None:
            known_set = set(known_pages)
            new_set = set(all_paths)
            added = sorted(new_set - known_set)
            removed = sorted(known_set - new_set)
            unchanged = sorted(known_set & new_set)

            if added:
                logger.info("New pages: %d", len(added))
            if removed:
                logger.info("Removed pages: %d", len(removed))

            return DiscoveryResult(
                all_pages=all_paths,
                added=added,
                removed=removed,
                unchanged=unchanged,
            )

        return DiscoveryResult(all_pages=all_paths)

    async def _scan_sitemap(self) -> list[str]:
        """Fetch and parse the sitemap (index or direct).

        Uses concurrent fetching for sub-sitemaps to speed up scanning.
        """
        async with httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT,
            follow_redirects=True,
        ) as client:
            # Step 1: Fetch the sitemap index
            try:
                response = await client.get(self.source.sitemap_url)
                if response.status_code != 200:
                    logger.error(
                        "Failed to fetch sitemap: HTTP %d", response.status_code
                    )
                    return []
            except httpx.HTTPError as e:
                logger.error("Error fetching sitemap: %s", e)
                return []

            # Step 2: Parse the sitemap index to find sub-sitemaps
            root = ET.fromstring(response.text)
            all_urls: list[str] = []

            # Check if this is a sitemap index (contains <sitemap> elements)
            sub_sitemaps = root.findall(
                "sm:sitemap/sm:loc", self.SITEMAP_NS
            )

            if sub_sitemaps:
                sitemap_urls = [s.text for s in sub_sitemaps if s.text]
                logger.info(
                    "Scanning %d sub-sitemaps concurrently...",
                    len(sitemap_urls),
                )

                # Fetch sub-sitemaps with limited concurrency (2)
                # Google rate-limits aggressive parallel requests
                _SITEMAP_CONCURRENCY = 2
                semaphore = asyncio.Semaphore(_SITEMAP_CONCURRENCY)
                tasks = [
                    self._fetch_sub_sitemap_with_semaphore(
                        client, url, semaphore
                    )
                    for url in sitemap_urls
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, list):
                        all_urls.extend(result)
                    elif isinstance(result, Exception):
                        logger.error("Sub-sitemap fetch error: %s", result)
            else:
                # This is a regular sitemap — extract URLs directly
                for url_elem in root.findall(
                    "sm:url/sm:loc", self.SITEMAP_NS
                ):
                    if url_elem.text:
                        all_urls.append(url_elem.text)

        # Filter by our source prefix
        filtered = [
            url
            for url in all_urls
            if self.source.sitemap_filter in url
        ]

        logger.info(
            "Filtered %d URLs matching '%s' (from %d total)",
            len(filtered),
            self.source.sitemap_filter,
            len(all_urls),
        )

        return filtered

    async def _fetch_sub_sitemap_with_semaphore(
        self,
        client: httpx.AsyncClient,
        sitemap_url: str,
        semaphore: asyncio.Semaphore,
    ) -> list[str]:
        """Fetch a sub-sitemap with concurrency control."""
        async with semaphore:
            return await self._fetch_sub_sitemap(client, sitemap_url)

    async def _fetch_sub_sitemap(
        self, client: httpx.AsyncClient, sitemap_url: str,
        _retries: int = 3,
    ) -> list[str]:
        """Fetch a single sub-sitemap and extract its URLs.

        Retries up to _retries times with exponential backoff on failure.
        """
        for attempt in range(1, _retries + 1):
            try:
                response = await client.get(sitemap_url)
                if response.status_code != 200:
                    logger.warning(
                        "HTTP %d for sub-sitemap %s",
                        response.status_code,
                        sitemap_url,
                    )
                    return []

                root = ET.fromstring(response.text)
                urls = []
                for url_elem in root.findall("sm:url/sm:loc", self.SITEMAP_NS):
                    if url_elem.text:
                        urls.append(url_elem.text)
                return urls

            except Exception as e:
                if attempt < _retries:
                    wait = 2 ** attempt  # 2s, 4s, 8s
                    logger.warning(
                        "Retry %d/%d for %s (waiting %ds): %s",
                        attempt, _retries, sitemap_url, wait, e,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        "Failed after %d retries for %s: %s",
                        _retries, sitemap_url, e,
                    )
                    return []

        return []  # Should not reach here

    def _url_to_path(self, url: str) -> str | None:
        """Convert a full URL to a relative path for this source.

        e.g. "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-1-pro"
             → "models/gemini/3-1-pro"
        """
        parsed = urlparse(url)
        full_path = parsed.path.rstrip("/")

        # Find the filter prefix in the path
        filter_clean = self.source.sitemap_filter.rstrip("/")
        if filter_clean in full_path:
            # Extract everything after the filter prefix
            idx = full_path.index(filter_clean) + len(filter_clean)
            relative = full_path[idx:].lstrip("/")
            return relative

        return None
