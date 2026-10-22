"""Split documents into chunks for retrieval.

Markdown is split along its own structure first: one chunk per "## " section, because a section
is a self-contained answer that can be cited ("Budgeting methods > The 50/30/20 rule"). A section
longer than `chunk_size` characters, and text or PDF documents (which have no headings), are cut
further by LangChain's RecursiveCharacterTextSplitter, which prefers paragraph, then sentence,
then word boundaries, with `overlap` characters repeated between neighbours so a sentence cut
in two is still whole in one of them.

The text that gets embedded and keyword-indexed is prefixed with the title and section
("Budgeting methods > The 50/30/20 rule"), which gives a bare paragraph its context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.documents import Document

DEFAULT_CHUNK_SIZE = 900
DEFAULT_OVERLAP = 150


@dataclass(frozen=True)
class KbChunk:
    document_id: str
    index: int
    section: str
    content: str
    metadata: dict = field(default_factory=dict)

    @property
    def search_text(self) -> str:
        title = self.metadata.get("title", "")
        heading = f"{title} > {self.section}" if self.section else title
        return f"{heading}\n{self.content}" if heading else self.content


def _sections(text: str) -> list[tuple[str, str]]:
    """(heading, body) pairs of a Markdown document; text before the first "## " has heading ""."""
    sections, heading, lines = [], "", []
    for line in [*text.splitlines(), "## "]:  # the sentinel closes the last section
        if line.startswith("## "):
            body = "\n".join(lines).strip()
            if body:
                sections.append((heading, body))
            heading, lines = line[3:].strip(), []
        elif not line.startswith("# "):  # the title is metadata, not content
            lines.append(line)
    return sections


def split_document(
    doc: Document, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP
) -> list[KbChunk]:
    if not 100 <= chunk_size <= 4000 or not 0 <= overlap < chunk_size // 2:
        raise ValueError("chunk_size must be 100-4000 and overlap under half of it")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=overlap, separators=["\n\n", "\n", ". ", " ", ""]
    )
    sections = _sections(doc.text) if doc.format == "md" else [("", doc.text)]
    base = {"title": doc.title, "topic": doc.topic, "source": doc.source, "version": doc.version}
    chunks: list[KbChunk] = []
    for heading, body in sections:
        body = re.sub(r"\n{3,}", "\n\n", body)
        for part in splitter.split_text(body) if len(body) > chunk_size else [body]:
            part = part.strip()
            if part:
                chunks.append(KbChunk(doc.id, len(chunks), heading[:200], part, dict(base)))
    return chunks
