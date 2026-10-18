"""POST /v1/help: answer a question about using the app from the help center, with citations.

The index (help sections, BM25 and embeddings) is built on the first question and reused.
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.rag.answer import answer_question
from app.rag.embeddings import load_embedder
from app.rag.knowledge import load_chunks
from app.rag.retriever import HelpIndex

router = APIRouter(prefix="/v1", tags=["help"])
logger = logging.getLogger("ml_service.rag")


class HelpRequest(BaseModel):
    question: str = Field(min_length=2, max_length=300)


class CitationOut(BaseModel):
    article: str
    title: str
    section: str


class HelpResponse(BaseModel):
    answer: str
    source: str = Field(description="llm (checked), extractive, or not_found")
    citations: list[CitationOut]


def get_help_index(request: Request) -> HelpIndex:
    state = request.app.state
    if state.help_index is None:
        settings = state.settings
        embedder = state.embedder or load_embedder(settings.embedding_model, settings.embedding_cache_dir)
        state.help_index = HelpIndex(load_chunks(settings.knowledge_dir), embedder)
        logger.info(
            "help index: %d sections, embeddings %s", len(state.help_index.chunks), embedder is not None
        )
    return state.help_index


@router.post("/help", response_model=HelpResponse, dependencies=[Depends(get_current_user)])
async def help_answer(body: HelpRequest, request: Request) -> HelpResponse:
    index = get_help_index(request)
    answer = await answer_question(
        index, body.question, request.app.state.llm, request.app.state.settings.llm_timeout_seconds
    )
    logger.info("help source=%s citations=%d", answer.source, len(answer.citations))
    request.app.state.metrics.event("help", answer.source)
    return HelpResponse(
        answer=answer.text,
        source=answer.source,
        citations=[CitationOut(**asdict(citation)) for citation in answer.citations],
    )
