"""The help center as retrievable chunks.

Articles are Markdown files in ml-service/knowledge/: a "# Title" and "## Section" headings.
Chunking follows that structure: one chunk per section, prefixed with its article title and
heading. A section is a self-contained answer, so it can be cited ("Exporting your data >
Opening the CSV in Excel"), and the prefix gives keyword and embedding search the context
that a bare paragraph lacks. Fixed-size windows, the common default, are kept for comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.config import DEFAULT_KNOWLEDGE_DIR


@dataclass(frozen=True)
class Chunk:
    id: str  # "exporting#opening-the-csv-in-excel"
    article: str  # file name without .md
    title: str  # the article's title
    section: str  # the section heading
    body: str  # the section's text

    @property
    def text(self) -> str:
        """What gets indexed: the body with its context."""
        return f"{self.title} > {self.section}\n{self.body}"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """An article's title and its (heading, text) sections."""
    title, sections, heading, lines = "", [], None, []
    for line in [*markdown.splitlines(), "## "]:  # the sentinel closes the last section
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            if heading:
                sections.append((heading, " ".join(" ".join(lines).split())))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line.strip())
    return title, sections


def load_chunks(knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR) -> list[Chunk]:
    chunks = []
    for path in sorted(Path(knowledge_dir).glob("*.md")):
        title, sections = _sections(path.read_text(encoding="utf-8"))
        chunks += [
            Chunk(f"{path.stem}#{_slug(heading)}", path.stem, title or path.stem, heading, body)
            for heading, body in sections if body
        ]
    return chunks


def _window(article: str, title: str, words: list[str], number: int) -> Chunk:
    return Chunk(f"{article}#w{number}", article, title, "", " ".join(words))


def fixed_size_chunks(chunks: list[Chunk], size: int = 300) -> list[Chunk]:
    """The same articles cut into windows of about `size` characters, ignoring sections."""
    windows = []
    by_article: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        by_article.setdefault(chunk.article, []).append(chunk)
    for article, parts in by_article.items():
        words = " ".join(part.body for part in parts).split()
        window: list[str] = []
        for word in words:
            window.append(word)
            if sum(len(w) + 1 for w in window) >= size:
                windows.append(_window(article, parts[0].title, window, len(windows)))
                window = []
        if window:
            windows.append(_window(article, parts[0].title, window, len(windows)))
    return windows
