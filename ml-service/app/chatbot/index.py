"""Build and load the chatbot's FAISS index.

    knowledge files -> LangChain Documents -> chunks -> MiniLM embeddings -> FAISS -> saved to disk

Only public material goes in here: help articles and financial education. Users' transactions
never do, because everyone shares this index. Render's free disk is wiped on restart, so the
Docker build runs training/build_index.py and the index ships inside the image; changing a
knowledge file therefore means a redeploy.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore, VectorStoreRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Groq has no embeddings, so these run here. FastEmbed runs the same MiniLM model on ONNX Runtime:
# sentence-transformers would need PyTorch, which doesn't fit the free server's 512 MB.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
SUPPORTED = (".md", ".txt", ".pdf")
_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"^## +(.+)$", re.MULTILINE)
_TITLE = re.compile(r"^# +(.+)$", re.MULTILINE)


def load_embeddings(cache_dir: Path) -> Embeddings:
    return FastEmbedEmbeddings(model_name=EMBEDDING_MODEL, cache_dir=str(cache_dir), threads=1)


def _load_file(path: Path) -> list[Document]:
    if path.suffix.lower() == ".pdf":
        return [page for page in PyPDFLoader(str(path)).load() if page.page_content.strip()]
    return TextLoader(str(path), encoding="utf-8").load()


def load_source_documents(root: Path) -> list[Document]:
    """Every knowledge file as Documents, with title, source and url from its front matter."""
    root = Path(root)
    documents = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED):
        for doc in _load_file(path):
            text, meta = doc.page_content, {}
            if match := _FRONT_MATTER.match(text):
                meta = yaml.safe_load(match.group(1)) or {}
                text = text[match.end() :]
            title = _TITLE.search(text)
            documents.append(
                Document(
                    page_content=text.strip(),
                    metadata={
                        "document": path.relative_to(root).with_suffix("").as_posix(),
                        "title": str(meta.get("title") or (title[1].strip() if title else path.stem)),
                        "source": str(meta.get("source") or "Expense Tracker help center"),
                        "url": meta.get("source_url"),
                        **({"page": doc.metadata["page"] + 1} if "page" in doc.metadata else {}),
                    },
                )
            )
    return documents


def split_documents(
    documents: list[Document], chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP
) -> list[Document]:
    """Chunks that prefer to break at section headings, each starting with its article's title
    so a passage keeps its context, and labelled with its section for the sources list."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n## ", "\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    chunks = []
    for doc in documents:
        headings = [(m.start(), m[1].strip()) for m in _HEADING.finditer(doc.page_content)]
        for chunk in splitter.split_documents([doc]):
            start = chunk.metadata.pop("start_index")
            # The section this chunk's text is mostly in: the last heading before its middle
            middle = start + len(chunk.page_content) // 2
            section = next((name for at, name in reversed(headings) if at <= middle), "")
            title = chunk.metadata["title"]
            chunk.page_content = f"{title}\n{chunk.page_content.strip()}"
            chunk.metadata["section"] = section
            chunks.append(chunk)
    return chunks


def build_vector_store(chunks: list[Document], embeddings: Embeddings) -> FAISS:
    return FAISS.from_documents(chunks, embeddings)


def save_index(store: FAISS, directory: Path) -> None:
    Path(directory).mkdir(parents=True, exist_ok=True)
    store.save_local(str(directory))


def load_index(directory: Path, embeddings: Embeddings) -> FAISS:
    """Reload without re-embedding. FAISS stores its documents with pickle, which can run code,
    so this must only ever load the index this project builds into its own image."""
    return FAISS.load_local(str(directory), embeddings, allow_dangerous_deserialization=True)


def make_retriever(store: VectorStore, k: int = 4) -> VectorStoreRetriever:
    return store.as_retriever(search_type="similarity", search_kwargs={"k": k})
