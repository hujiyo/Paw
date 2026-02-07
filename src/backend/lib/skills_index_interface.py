"""Utility APIs for consuming the skills-index.md format.

This module exposes a tiny, dependency-free client class that can:
- Connect to a remote GitHub repo, raw URL, or local file containing a skills-index.md
- Parse the canonical >start/>end format with categories (~) and optional [简介]
- Provide helper methods to inspect categories, list entries, and run fuzzy searches

Copied and adapted from https://github.com/hujiyo/skills-index (Apache-2.0).
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class SkillsIndexEntry:
    """Represents a single repository reference inside skills-index.md."""

    repository: str
    owner: str
    name: str
    subpath: Optional[str]
    category: str
    description: Optional[str]

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Return a JSON-serializable dictionary representation of the entry."""

        return asdict(self)


class SkillsIndexHub:
    """A lightweight parser and query helper for the Skills Index format."""

    DEFAULT_SOURCE = "https://raw.githubusercontent.com/hujiyo/skills-index/master/skills-index.md"

    def __init__(self) -> None:
        self._source: Optional[str] = None
        self._raw_text: str = ""
        self._entries: List[SkillsIndexEntry] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def connect(self, source: Optional[str] = None, *, force_refresh: bool = False) -> None:
        """Load and parse a skills-index source.

        Args:
            source: One of
                - ``None`` (default): use last-connected source or the canonical repo
                - A local ``.md`` file path
                - An HTTP(S) URL pointing to a raw skills-index file
                - A ``owner/repo`` GitHub shorthand
            force_refresh: When ``True``, always re-download/read even if cached
        """

        target = source or self._source or self.DEFAULT_SOURCE

        # Skip when the same source is already parsed, unless forced.
        if not force_refresh and self._entries and target == self._source:
            return

        text = self._load_source(target)
        self._source = target
        self._raw_text = text
        self._entries = self._parse_index(text)

    def list_categories(self) -> List[str]:
        """Return all distinct category names (sorted)."""

        self._ensure_connected()
        return sorted({entry.category for entry in self._entries})

    def list_entries(self) -> List[Dict[str, Optional[str]]]:
        """Return every entry in insertion order, as dictionaries."""

        self._ensure_connected()
        return [entry.to_dict() for entry in self._entries]

    def list_entries_by_category(self, category: str) -> List[Dict[str, Optional[str]]]:
        """Return entries that belong to the given category name (case-insensitive)."""

        if not category:
            raise ValueError("category must be a non-empty string")

        self._ensure_connected()
        category_lower = category.lower()
        return [
            entry.to_dict()
            for entry in self._entries
            if entry.category.lower() == category_lower
        ]

    def search_entries(
        self,
        keyword: str,
        *,
        category: Optional[str] = None,
    ) -> List[Dict[str, Optional[str]]]:
        """Fuzzy search entries by keyword inside repository path or description.

        Args:
            keyword: Search string. Empty keywords return an empty list.
            category: Optional category filter (case-insensitive). When omitted,
                the search spans all categories.
        """

        if not keyword:
            return []

        self._ensure_connected()
        keyword_lower = keyword.lower()
        category_lower = category.lower() if category else None

        matches: List[Dict[str, Optional[str]]] = []
        for entry in self._entries:
            if category_lower and entry.category.lower() != category_lower:
                continue

            haystacks = [entry.repository.lower()]
            if entry.description:
                haystacks.append(entry.description.lower())

            if any(keyword_lower in hay for hay in haystacks):
                matches.append(entry.to_dict())

        return matches

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ensure_connected(self) -> None:
        if not self._entries:
            raise RuntimeError(
                "No skills-index loaded yet. Call `connect()` before accessing data."
            )

    def _load_source(self, target: str) -> str:
        """Load the raw index text from the supported target formats."""

        # HTTP(S) URL
        if target.startswith("http://") or target.startswith("https://"):
            # 对于 hujiyo/skills-index 官方索引，尝试 GitHub 失败后使用 Gitee 镜像
            if "hujiyo/skills-index" in target and "github.com" in target:
                try:
                    with urllib.request.urlopen(target, timeout=15) as resp:
                        return resp.read().decode("utf-8")
                except urllib.error.URLError:
                    # GitHub 访问失败，尝试 Gitee 镜像
                    gitee_target = target.replace(
                        "https://raw.githubusercontent.com/hujiyo/skills-index/HEAD",
                        "https://gitee.com/hujiyo/skills-index/raw/HEAD"
                    ).replace(
                        "https://api.github.com/repos/hujiyo/skills-index/contents/skills-index.md",
                        "https://gitee.com/hujiyo/skills-index/raw/HEAD/skills-index.md"
                    )
                    try:
                        with urllib.request.urlopen(gitee_target, timeout=15) as resp:
                            return resp.read().decode("utf-8")
                    except urllib.error.URLError as exc:
                        raise RuntimeError(f"Failed to fetch skills index from both GitHub and Gitee: {exc}")
            else:
                try:
                    with urllib.request.urlopen(target, timeout=15) as resp:
                        return resp.read().decode("utf-8")
                except urllib.error.URLError as exc:
                    raise RuntimeError(f"Failed to fetch skills index from {target}: {exc}")

        # Local file path
        path = Path(target)
        if path.exists():
            return path.read_text(encoding="utf-8")

        # GitHub shorthand "owner/repo"
        if "/" in target:
            owner_repo = target.strip().strip("/")
            # 特殊处理 hujiyo/skills-index：优先 GitHub，失败则使用 Gitee
            if owner_repo.lower() == "hujiyo/skills-index":
                github_url = f"https://raw.githubusercontent.com/hujiyo/skills-index/HEAD/skills-index.md"
                try:
                    return self._load_source(github_url)
                except RuntimeError:
                    # GitHub 失败，使用 Gitee 镜像
                    gitee_url = f"https://gitee.com/hujiyo/skills-index/raw/HEAD/skills-index.md"
                    try:
                        with urllib.request.urlopen(gitee_url, timeout=15) as resp:
                            return resp.read().decode("utf-8")
                    except urllib.error.URLError as exc:
                        raise RuntimeError(f"Failed to fetch skills index from both GitHub and Gitee: {exc}")
            else:
                raw_url = f"https://raw.githubusercontent.com/{owner_repo}/HEAD/skills-index.md"
                return self._load_source(raw_url)

        raise ValueError(
            "Unsupported source format. Provide a local .md file, HTTP(S) URL, or owner/repo."
        )

    def _parse_index(self, text: str) -> List[SkillsIndexEntry]:
        entries: List[SkillsIndexEntry] = []
        in_index = False
        current_category = "index list"

        line_pattern = re.compile(r"^(?P<repo>[^\[]+?)(?:\[(?P<desc>.*)\])?$")

        for raw_line in text.splitlines():
            line = raw_line.strip()

            if not line:
                continue
            if line.startswith("#"):
                continue

            lowered = line.lower()
            if lowered == ">start":
                in_index = True
                current_category = "index list"
                continue
            if lowered == ">end":
                break
            if not in_index:
                continue

            if line.startswith("~"):
                current_category = line[1:].strip() or "not categorized"
                continue

            if "/" not in line:
                continue

            match = line_pattern.match(line)
            if not match:
                continue

            repo_path = match.group("repo").strip()
            description = match.group("desc")
            description = description.strip() if description else None

            parts = [part for part in repo_path.split("/") if part]
            if len(parts) < 2:
                continue

            owner, name, *rest = parts
            subpath = "/".join(rest) if rest else None
            canonical_repo = f"{owner}/{name}" + (f"/{subpath}" if subpath else "")

            entries.append(
                SkillsIndexEntry(
                    repository=canonical_repo,
                    owner=owner,
                    name=name,
                    subpath=subpath,
                    category=current_category,
                    description=description,
                )
            )

        if not entries:
            raise RuntimeError("No valid entries found inside skills-index.md")

        return entries


__all__ = ["SkillsIndexHub", "SkillsIndexEntry"]
