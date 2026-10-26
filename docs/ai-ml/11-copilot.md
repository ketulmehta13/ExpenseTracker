# 11. The Financial Copilot (RAG + tools)

The assistant grew into a copilot that answers three kinds of questions and keeps them apart:

| | Example | Answered from | How |
|---|---|---|---|
| **A** knowledge | "Explain the 50/30/20 budgeting rule" | the knowledge base | retrieval + an LLM answer that must cite its passages |
| **B** your data | "How much did I spend on food last month?" | your transactions | a typed analytics tool; exact figures in a template |
| **C** both | "My food spending went up. Why, and what budget method helps?" | tools, then the knowledge base | facts first, then cited advice; the model writes `[placeholders]` for your figures |
| **D** neither | "What's the capital of Australia?" | — | says so, and what it can do instead |

Plus actions ("add 450 swiggy yesterday", "set my budget to 30000") that you edit and confirm, and small talk.

**RAG is never used for your numbers.** Totals come from code with exact decimal arithmetic. The LLM only words answers. It never computes, chooses or copies a figure, and its answer is checked before it is final.

## Architecture

```
Browser (Vercel)                    ml-service (FastAPI on Render)                          Supabase
────────────────                    ───────────────────────────────                         ────────
CopilotPanel  ──POST /v1/copilot/chat/stream (JWT)──►  verify JWT · per-user rate limit
  SSE: meta, delta…, final ◄──────                     load the user's data with THEIR token ──────► transactions, categories,
                                                        (cached 60 s)                                 profiles (RLS)
                                                        history: open thread, last messages ───────► chat_threads/messages (RLS)
                                                        LangGraph:
                                                          route ──► tools ──► retrieve ──► compose
                                                            │         (allowlisted,  (gte-small +     (template, or LLM +
                                                            │          typed, Decimal) BM25, RRF)      grounding check)
                                                            │                    └── match_kb_chunks() ──► kb_chunks (pgvector)
                                                            │                        fallback: snapshot baked into the image
                                                            └─► action: proposal block (nothing written)
ActionCard ──POST /v1/copilot/actions/confirm──►  validate again · claim idempotency key ───────────► copilot_actions (unique)
                                                  write as the user ──────────────────────────────► transactions / profiles
LLM: Groq (OpenAI-compatible), via LangChain ChatOpenAI; any provider by configuration.
Ingestion (GitHub Actions, service-role key as a secret): knowledge/ ─► chunk ─► embed ─► upsert ──► kb_documents/kb_chunks
```

### Components

| Module | Responsibility |
|---|---|
| `app/rag/documents.py` | Load Markdown (with YAML front matter), TXT and PDF; metadata: id, title, source, source_url, topic, version, references |
| `app/rag/chunking.py` | One chunk per `##` section, then LangChain's `RecursiveCharacterTextSplitter` (900 chars, 150 overlap) for long sections and headingless files |
| `app/rag/ingest.py` | Incremental ingestion: a fingerprint of content + metadata + chunking. Unchanged documents are skipped, changed ones have all their chunks replaced, removed ones are deleted |
| `app/rag/vectorstore.py` | `SupabaseVectorStore` (pgvector over REST + RPC), `InMemoryVectorStore` (tests, evaluation), a snapshot file, and a fallback wrapper |
| `app/rag/kb_retriever.py` | Hybrid search (gte-small cosine + BM25, fused with RRF), topic filters, a sufficiency check calibrated on dev questions |
| `app/copilot/routing.py` | Deterministic routing A/B/C/D, plus action and small talk; reuses the assistant's slot filling (periods, your categories, merchants, follow-ups) |
| `app/copilot/tools.py` | Read tools: `get_expense_summary`, `compare_expense_periods`, `get_category_breakdown`, `get_budget_status`, `detect_recurring_expenses`, `get_unusual_payments`; the allowlist for LLM tool calling |
| `app/copilot/facts.py` | Tool results become named facts, template sentences and chart/table blocks |
| `app/copilot/prompts.py`, `compose.py` | Grounded prompts (evidence fenced as data), the grounding check, fallbacks, streaming with on-the-fly placeholder filling |
| `app/copilot/actions.py` | Proposals, server-side validation, idempotent execution |
| `app/copilot/history.py` | Conversations in Supabase, read and written as the user |
| `app/copilot/pipeline.py` | The LangGraph workflow |
| `app/routers/copilot.py` | The HTTP API |
| `frontend/src/components/copilot/` | The panel: streaming, Stop, Retry, history, citations, charts, editable action cards |

### Why these choices

- **A workflow, not an agent loop.** Each message is routed once and each step runs at most once. That is predictable, testable and cheap. The LLM is used in two bounded places: wording a grounded answer, and choosing one allowlisted tool when the rules don't recognise a personal question.
- **gte-small in the service, pgvector in Supabase.** The model needs about 80 MB of memory, measured. The whole service with OCR loaded uses about 345 MB, inside the free 512 MB. Vectors live in Postgres, so the knowledge base can be updated without a redeploy. The previous help search ran keyword-only in production, because its bge-small model needed about 370 MB.
- **Hybrid retrieval.** Keywords catch exact terms ("SIP", "CSV"); embeddings catch paraphrases ("rainy day money" → emergency fund). The evaluation below shows hybrid search beating each one alone.
- **Placeholders instead of number checks.** An earlier experiment in this project (06-llm.md) found that checking the model's numbers against the facts lets a real number next to the wrong words pass. So in combined answers the model writes `[spent]`, and code substitutes the value. Any digit the model writes itself must appear in a source it cites.

## API

All routes need `Authorization: Bearer <Supabase access token>`. The user id always comes from the verified token.

| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/v1/copilot/chat` | `{message (1–1000 chars), thread_id?, today?}` | `CopilotReply` |
| POST | `/v1/copilot/chat/stream` | same | SSE: `meta {thread_id}`, `delta {text}`…, then `final CopilotReply` or `error {message}` |
| POST | `/v1/copilot/actions/confirm` | `{action, idempotency_key, fields, thread_id?, today?}` | `{status: done\|duplicate, reply, result}` |
| GET | `/v1/copilot/threads` | — | `[{id, title, updated_at}]` |
| GET | `/v1/copilot/threads/{id}` | — | `[{role, content, blocks, created_at}]` |
| DELETE | `/v1/copilot/threads/{id}` | — | 204 |

`CopilotReply = {thread_id, route, reply, blocks[], grounded, answered_by: template|llm|extractive|fixed, history_saved}`. The `blocks` are typed:
- `citations`: `{n, ref, title, section, source, source_url, topic, version, excerpt}`;
- `chart`: `bar` or `comparison` points;
- `data`: a tool's result;
- `action`: the proposed fields, an idempotency key and a summary.

The final text of a stream replaces the streamed text, because that is the checked version.

Errors:
- 401 for a missing or invalid token;
- 404 for a thread you don't own (it is indistinguishable from one that doesn't exist);
- 422 for invalid confirmed fields;
- 429 with `Retry-After` when rate limited (20 a minute, 300 a day per user);
- 503 for history when the tables are missing.

## Security

- **Isolation.** Data and history are read and written with the user's own JWT, so Postgres row level security applies. The service never holds the service-role key. Tests check that another user can't read, continue or delete a conversation, and that their transactions never appear in an answer.
- **Tools.** There is an allowlist. Arguments are validated by Pydantic, and unknown arguments (such as a `user_id` the model invented) are rejected. There is no SQL and no tool that takes a user id.
- **Writes.** Nothing is saved without an explicit confirmation. The server validates again: amount range, date within five years, and that the category is one of the user's own. An idempotency key is claimed first in `copilot_actions`, unique per user, so a double click or a retry runs the write once.
- **Prompt injection.** The knowledge base is written only by the ingestion job. Retrieved text and tool facts are fenced as data in the prompt. The model has no tools it can call on its own, and its output is checked before it is shown: citations, numbers, placeholders, no markup, length. The UI renders text only, never HTML.
- **Logs** record the route, how the answer was produced, and timing. They never contain message text or figures.
- **Graceful degradation:**
  - no LLM, a timeout or a 429 → a cited quoted passage, or the template answer;
  - pgvector down → the baked snapshot, then keywords only;
  - history tables missing → the answer still arrives, with `history_saved: false`;
  - the `copilot_actions` table missing → idempotency per process.

## Evaluation

Reproduce with `python -m training.evaluate_copilot_retrieval --gate` and `python -m training.evaluate_copilot --gate` (both run in CI), or add `--llm` to the second with an LLM configured. Reports: [`reports/copilot_retrieval/report.md`](../../ml-service/reports/copilot_retrieval/report.md) and [`reports/copilot/report.md`](../../ml-service/reports/copilot/report.md).

| What | Result (test sets, never tuned on) |
|---|---|
| Retrieval, hybrid (51 questions: app help, finance, off-topic) | hit@1 **0.902**, hit@3 0.961, MRR@5 0.936; answer-or-decline correct 0.966 |
| Retrieval, keywords only / dense only | hit@1 0.863 / 0.863 |
| Routing (31 messages incl. adversarial) | route **0.968**, route + tools 0.935 (2 misses, listed in the report) |
| Financial correctness (25 simulated users × 4 periods) | **1049 / 1049** figures exact against an integer-paise oracle |
| Grounding check | 84 / 84 planted failures rejected; 21 / 21 correct cited answers accepted |
| End to end with Groq `openai/gpt-oss-120b` | 9 of 13 knowledge/combined answers from the model passed the check; 3 fell back to a cited passage (one after a free-tier 429); 1 judged the evidence insufficient although the emergency-fund article answers it |
| Latency | data 4 ms; knowledge 0.85 s median with the LLM, 10 ms without it; combined 1.7 s median |
| Cost | ₹0 (Groq free tier, rate-limited); embeddings run locally |

What the numbers don't show: the knowledge base is small (21 documents) and written for this app, and the test questions were written by the same person as the rules. Real users will phrase things these sets don't cover, so the misses in the reports are the place to start.

## Deployment

1. **Run the migration.** Paste `supabase/migrations/20261022000000_copilot.sql` into the Supabase SQL editor and run it; it can be run more than once. It enables pgvector and creates the knowledge, history and action tables with their policies. Until it runs, the copilot still answers: from the snapshot, without saved history, and with idempotency per process.
2. **Ingest the knowledge base.** In GitHub, open Settings → Secrets → Actions and add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`. Then run the **Ingest knowledge base** workflow, or push a change under `ml-service/knowledge/`. Locally: `python -m training.ingest_kb --dry-run`, then without `--dry-run`.
3. **Render.** Nothing new is required. `COPILOT_EMBEDDING_MODEL` (default `Supabase/gte-small`; `none` means keywords only), `COPILOT_PER_MINUTE` and `COPILOT_PER_DAY` are optional. The Docker build bakes gte-small and the knowledge snapshot into the image. Server-sent events work on Render; free instances still sleep, so keep the Supabase pg_cron ping from 09-mlops.md.
4. **Vercel.** Nothing new: the panel uses the existing `VITE_ML_API_URL`.

**Adding or updating knowledge:**
- add a file under `ml-service/knowledge/` (`.md` with front matter, `.txt` or `.pdf`) and push;
- the workflow ingests only what changed, and deleting a file deletes its chunks;
- bump `version:` in the front matter when the meaning changes.

**Rollback:**
- Revert the merge commit. The old `/v1/assistant` endpoints are still served, and the previous frontend used them.
- The migration only adds tables, so it can stay. To remove them, drop `copilot_actions`, `chat_messages`, `chat_threads`, `kb_chunks`, `kb_documents` and the `match_kb_chunks` function.

## Interview questions this answers

- *When is RAG the wrong tool?* For a user's own numbers. Those come from queries and code, and RAG supplies only the explanation around them.
- *How do you stop an LLM from inventing figures?* It never writes them. It writes placeholders, code fills in values it computed, and an answer that fails the check is replaced.
- *How do you evaluate a RAG system?* Separately at each layer: retrieval (hit@k, decline accuracy), routing, financial correctness, grounding (planted failures), then end to end with the real model, reporting the fallbacks rather than hiding them.
- *How do you make writes from a chatbot safe?* Proposals, explicit confirmation, server-side validation, idempotency keys, and the user's own token with row level security.
