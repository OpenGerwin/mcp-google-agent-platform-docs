"""Source configuration model.

Loads YAML source definitions (GEAP, Vertex AI, etc.) and provides
a structured representation for use by other components.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config

logger = logging.getLogger(__name__)


@dataclass
class Section:
    """A documentation section (e.g. 'Agents → Build', 'Models')."""

    id: str
    name: str
    path_prefixes: list[str]
    description: str = ""


@dataclass
class Source:
    """Represents a documentation source (GEAP, Vertex AI, etc.)."""

    id: str
    name: str
    short_name: str
    enabled: bool
    base_url: str
    sitemap_url: str
    sitemap_filter: str
    sections: list[Section] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> Source:
        """Load a source configuration from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        sections = []
        for section_id, section_data in data.get("sections", {}).items():
            sections.append(
                Section(
                    id=section_id,
                    name=section_data["name"],
                    path_prefixes=section_data.get("path_prefixes", []),
                    description=section_data.get("description", ""),
                )
            )

        return cls(
            id=data["id"],
            name=data["name"],
            short_name=data["short_name"],
            enabled=data.get("enabled", True),
            base_url=data["base_url"].rstrip("/"),
            sitemap_url=data["sitemap_url"],
            sitemap_filter=data["sitemap_filter"],
            sections=sections,
        )

    def categorize_path(self, path: str) -> str:
        """Assign a URL path to a section based on prefix matching.

        Returns the section ID, or 'uncategorized' if no match.
        """
        for section in self.sections:
            for prefix in section.path_prefixes:
                if prefix and path.startswith(prefix):
                    return section.id
        return "uncategorized"

    def get_section(self, section_id: str) -> Section | None:
        """Get a section by its ID."""
        for section in self.sections:
            if section.id == section_id:
                return section
        return None


def load_sources(sources_dir: Path | None = None) -> dict[str, Source]:
    """Load all source configurations from YAML files.

    Returns a dict mapping source ID → Source object.
    Only enabled sources are included.
    """
    if sources_dir is None:
        sources_dir = config.SOURCES_DIR

    sources: dict[str, Source] = {}

    if not sources_dir.exists():
        logger.warning("Sources directory not found: %s", sources_dir)
        return sources

    for yaml_path in sorted(sources_dir.glob("*.yaml")):
        try:
            source = Source.from_yaml(yaml_path)
            if source.enabled:
                sources[source.id] = source
                logger.info("Loaded source: %s (%s)", source.id, source.name)
            else:
                logger.debug("Skipping disabled source: %s", source.id)
        except Exception as e:
            logger.error("Failed to load source from %s: %s", yaml_path, e)

    return sources
