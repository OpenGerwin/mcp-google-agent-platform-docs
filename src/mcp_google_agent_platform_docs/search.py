"""Lightweight TF-IDF search engine for cached documentation.

No external dependencies — pure Python implementation.
Builds an inverted index from cached markdown documents and supports
ranked search with excerpt extraction.
"""

from __future__ import annotations

import math
import re
import logging
from collections import Counter
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Common English stop words to ignore in indexing
STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "has", "have", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "shall", "this", "that",
    "these", "those", "it", "its", "not", "no", "if", "then", "else",
    "when", "where", "how", "what", "which", "who", "whom", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "than",
    "too", "very", "just", "about", "above", "after", "again", "also",
    "any", "because", "before", "between", "during", "into", "out", "over",
    "own", "same", "so", "under", "until", "up", "while", "you", "your",
    "use", "using", "used",
})


@dataclass
class SearchResult:
    """A single search result."""

    path: str
    title: str
    score: float
    excerpt: str
    source_id: str


class SearchEngine:
    """Simple TF-IDF search engine across cached documents."""

    def __init__(self):
        # {token: {path: count}}
        self._inverted_index: dict[str, dict[str, int]] = {}
        # {path: total_token_count}
        self._doc_lengths: dict[str, int] = {}
        # {path: raw_content}
        self._documents: dict[str, str] = {}
        # {path: title}
        self._titles: dict[str, str] = {}
        # {path: source_id}
        self._sources: dict[str, str] = {}
        # Total document count
        self._num_docs: int = 0

    def build_index(self, pages: dict[str, str], source_id: str) -> None:
        """Build (or extend) the index from {path: content} dict.

        Can be called multiple times for different sources.
        """
        for path, content in pages.items():
            unique_key = f"{source_id}:{path}"

            # Extract title (first H1 or first line)
            title = self._extract_title(content)
            self._titles[unique_key] = title
            self._documents[unique_key] = content
            self._sources[unique_key] = source_id

            # Tokenize
            tokens = self._tokenize(content)
            self._doc_lengths[unique_key] = len(tokens)

            # Build inverted index
            token_counts = Counter(tokens)
            for token, count in token_counts.items():
                if token not in self._inverted_index:
                    self._inverted_index[token] = {}
                self._inverted_index[token][unique_key] = count

        self._num_docs = len(self._documents)
        logger.info(
            "Index built/updated: %d total docs, %d unique tokens",
            self._num_docs,
            len(self._inverted_index),
        )

    def search(
        self,
        query: str,
        max_results: int = 5,
        source_id: str | None = None,
    ) -> list[SearchResult]:
        """Search for documents matching the query.

        Args:
            query: Search terms.
            max_results: Max number of results to return.
            source_id: Filter by source (None = search all).

        Returns:
            Ranked list of SearchResult objects.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        # Calculate TF-IDF scores for each document
        scores: dict[str, float] = {}

        for token in query_tokens:
            if token not in self._inverted_index:
                continue

            posting = self._inverted_index[token]
            # IDF: log(N / df)
            df = len(posting)
            idf = math.log(self._num_docs / df) if df > 0 else 0

            for unique_key, tf in posting.items():
                # Filter by source if specified
                if source_id and self._sources.get(unique_key) != source_id:
                    continue

                # TF: normalized by document length
                doc_len = self._doc_lengths.get(unique_key, 1)
                normalized_tf = tf / doc_len

                score = normalized_tf * idf
                scores[unique_key] = scores.get(unique_key, 0.0) + score

        # Sort by score (descending) and take top results
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ranked = ranked[:max_results]

        results = []
        for unique_key, score in ranked:
            src_id = self._sources[unique_key]
            path = unique_key.split(":", 1)[1]
            content = self._documents[unique_key]

            results.append(
                SearchResult(
                    path=path,
                    title=self._titles.get(unique_key, path),
                    score=round(score, 6),
                    excerpt=self._extract_excerpt(content, query),
                    source_id=src_id,
                )
            )

        return results

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text: lowercase, split on non-alpha, remove stop words."""
        # Convert to lowercase and split on non-alphanumeric
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        # Remove stop words and very short tokens
        return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

    def _extract_title(self, content: str) -> str:
        """Extract the first H1 heading as the title."""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# ") and not line.startswith("##"):
                return line[2:].strip()
        # Fallback: first non-empty line
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith(">") and not line.startswith("<!--"):
                return line[:100]
        return ""

    def _extract_excerpt(
        self, content: str, query: str, chars: int = 300
    ) -> str:
        """Extract a relevant excerpt around the first query match."""
        content_lower = content.lower()
        query_lower = query.lower()

        # Try to find exact phrase match first
        idx = content_lower.find(query_lower)

        if idx == -1:
            # Try individual words
            for word in query_lower.split():
                if len(word) > 2:
                    idx = content_lower.find(word)
                    if idx != -1:
                        break

        if idx == -1:
            # No match found — return start of document
            return content[:chars].strip() + "..."

        # Extract context around the match
        start = max(0, idx - chars // 3)
        end = min(len(content), idx + chars * 2 // 3)

        excerpt = content[start:end].strip()

        # Clean up: don't start/end mid-word
        if start > 0:
            space_idx = excerpt.find(" ")
            if space_idx != -1 and space_idx < 30:
                excerpt = "..." + excerpt[space_idx + 1 :]

        if end < len(content):
            space_idx = excerpt.rfind(" ")
            if space_idx != -1 and space_idx > len(excerpt) - 30:
                excerpt = excerpt[:space_idx] + "..."

        return excerpt

    @property
    def doc_count(self) -> int:
        """Total number of indexed documents."""
        return self._num_docs
