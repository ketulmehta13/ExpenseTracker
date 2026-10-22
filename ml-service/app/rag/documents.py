"""Knowledge-base documents: files in ml-service/knowledge/ with their metadata.

Supported formats: Markdown (.md), plain text (.txt) and PDF (.pdf, its text layer). A Markdown
file may start with YAML front matter:

    ---
    title: Budgeting methods
    topic: budgeting
    source: Expense Tracker editorial
    source_url: https://www.ncfe.org.in/
    version: 2
    ---

Anything missing is derived: the id from the path ("finance/budgeting-methods"), the topic from
the folder ("finance" files must set one), the title from the first "# " heading or the file name.
A document's sha256 covers its text and metadata, so ingestion can tell what changed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SUPPORTED_SUFFIXES = (".md", ".txt", ".pdf")
DEFAULT_SOURCE = "Expense Tracker help center"
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_ID = re.compile(r"^[a-z0-9][a-z0-9/_-]{1,119}$")
_TOPIC = re.compile(r"^[a-z0-9-]{1,40}$")


class DocumentError(ValueError):
    """A knowledge file that can't be ingested (bad metadata, unreadable, empty)."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    text: str  # the body, front matter removed; Markdown keeps its headings
    topic: str
    source: str = DEFAULT_SOURCE
    source_url: str | None = None
    version: int = 1
    format: str = "md"
    references: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sha256(self) -> str:
        meta = [self.title, self.topic, self.source, self.source_url, self.version, list(self.references)]
        return hashlib.sha256((json.dumps(meta) + "\n" + self.text).encode("utf-8")).hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def document_id(path: Path, root: Path) -> str:
    """ "finance/Budgeting Methods.md" -> "finance/budgeting-methods"."""
    parts = path.relative_to(root).with_suffix("").parts
    return "/".join(_slug(part) for part in parts)


def _read_pdf(path: Path) -> str:
    import pypdfium2 as pdfium

    try:
        document = pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as err:
        raise DocumentError(f"{path.name}: can't open the PDF ({err})") from err
    try:
        pages = [document[index].get_textpage().get_text_range() for index in range(len(document))]
    finally:
        document.close()
    return "\n\n".join(page.strip() for page in pages if page.strip())


def load_document(path: Path, root: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise DocumentError(f"{path.name}: unsupported format (use {', '.join(SUPPORTED_SUFFIXES)})")
    raw = _read_pdf(path) if suffix == ".pdf" else path.read_text(encoding="utf-8")
    meta: dict = {}
    if match := _FRONT_MATTER.match(raw):
        try:
            meta = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as err:
            raise DocumentError(f"{path.name}: invalid front matter ({err})") from err
        if not isinstance(meta, dict):
            raise DocumentError(f"{path.name}: front matter must be key: value pairs")
        raw = raw[match.end() :]
    text = raw.strip()
    if not text:
        raise DocumentError(f"{path.name}: no text")

    doc_id = str(meta.get("id") or document_id(path, root))
    heading = re.search(r"^# (.+)$", text, re.MULTILINE)
    folder = path.relative_to(root).parts[0] if len(path.relative_to(root).parts) > 1 else "app-help"
    topic = str(meta.get("topic") or ("app-help" if folder == "app-help" else ""))
    title = str(meta.get("title") or (heading.group(1).strip() if heading else path.stem.replace("-", " ")))
    source_url = meta.get("source_url")
    references = tuple(str(url) for url in meta.get("references") or ())
    version = meta.get("version", 1)

    if not _ID.match(doc_id):
        raise DocumentError(f"{path.name}: invalid id {doc_id!r}")
    if not _TOPIC.match(topic):
        raise DocumentError(f"{path.name}: set a topic in the front matter (lowercase words and hyphens)")
    if source_url is not None and not str(source_url).startswith("https://"):
        raise DocumentError(f"{path.name}: source_url must be an https:// link")
    if any(not url.startswith("https://") for url in references):
        raise DocumentError(f"{path.name}: references must be https:// links")
    if not isinstance(version, int) or version < 1:
        raise DocumentError(f"{path.name}: version must be a positive whole number")
    return Document(
        id=doc_id,
        title=title[:200],
        text=text,
        topic=topic,
        source=str(meta.get("source") or DEFAULT_SOURCE)[:200],
        source_url=str(source_url) if source_url else None,
        version=version,
        format=suffix.lstrip("."),
        references=references,
    )


def load_documents(root: Path) -> list[Document]:
    """Every supported file under root, in a stable order. Duplicate ids are an error."""
    root = Path(root)
    documents = [
        load_document(path, root)
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and not path.name.startswith(("_", "."))
    ]
    seen: dict[str, str] = {}
    for doc in documents:
        if doc.id in seen:
            raise DocumentError(f"duplicate document id {doc.id!r}")
        seen[doc.id] = doc.title
    return documents
