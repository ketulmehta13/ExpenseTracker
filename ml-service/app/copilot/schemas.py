"""The copilot's API contract.

A reply is plain text plus typed blocks; the UI renders each block type with its own component
and never renders HTML from the model:
- citations: the knowledge-base passages the answer used, numbered as cited in the text ([S1]);
- chart: category bars or a period comparison, from a tool's exact figures;
- data: a tool's full result (summary, budget, subscriptions, unusual payments) for a table;
- action: a proposed write (a transaction, a budget) that the user can edit and must confirm.
A hidden "context" block is stored with assistant messages so follow-ups ("and last month?")
keep the previous question's period, category and merchant.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Route = Literal["knowledge", "data", "combined", "action", "small_talk", "unsupported"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    thread_id: UUID | None = None  # omit to start a new conversation
    today: date | None = None


class Citation(BaseModel):
    n: int  # as cited in the text: [S1]
    ref: str  # "finance/budgeting-methods#1"
    title: str
    section: str
    source: str
    source_url: str | None
    topic: str
    version: int
    excerpt: str


class CitationsBlock(BaseModel):
    type: Literal["citations"] = "citations"
    items: list[Citation]


class ChartPoint(BaseModel):
    label: str
    value: float
    previous: float | None = None


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    chart: Literal["bar", "comparison"]
    title: str
    unit: Literal["INR"] = "INR"
    points: list[ChartPoint]


class DataBlock(BaseModel):
    type: Literal["data"] = "data"
    tool: str
    result: dict


class TransactionFields(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, le=10_000_000)
    date: date
    type: Literal["INCOME", "EXPENSE"]
    category_id: int | str | None = None
    category_name: str | None = None


class BudgetFields(BaseModel):
    monthly_budget: float = Field(ge=0, le=100_000_000)
    previous_budget: float | None = None


class ActionBlock(BaseModel):
    type: Literal["action"] = "action"
    action: Literal["create_transaction", "update_budget"]
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    fields: TransactionFields | BudgetFields
    summary: str


class ContextBlock(BaseModel):
    type: Literal["context"] = "context"
    understanding: dict


Block = Annotated[
    CitationsBlock | ChartBlock | DataBlock | ActionBlock | ContextBlock, Field(discriminator="type")
]


class CopilotReply(BaseModel):
    thread_id: UUID | None  # None when history couldn't be saved
    route: Route
    reply: str
    blocks: list[Block] = Field(default_factory=list)
    grounded: bool  # every statement came from tools or cited sources
    answered_by: Literal["template", "llm", "extractive", "fixed"]
    history_saved: bool


class ConfirmRequest(BaseModel):
    action: Literal["create_transaction", "update_budget"]
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    fields: dict
    thread_id: UUID | None = None
    today: date | None = None


class ConfirmResult(BaseModel):
    status: Literal["done", "duplicate"]
    reply: str
    result: dict


class ThreadSummary(BaseModel):
    id: UUID
    title: str
    updated_at: str


class StoredMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    blocks: list[dict]
    created_at: str
