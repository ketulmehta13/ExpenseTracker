# AI/ML in Expense Tracker

Every AI/ML feature in this project is documented here: what it does, the technique behind it, how it is evaluated, and the trade-offs. Each page is written so the feature can be explained in an interview.

## Principles

- **Baseline first.** Every model starts with a simple, measurable baseline. Anything fancier has to beat it on the same test set.
- **No paid APIs.** Classical ML runs in `ml-service/`. LLM features use open models (Ollama locally, or a free hosted tier) behind LangChain's chat-model interface, so the provider is a config value.
- **Users' data stays theirs.** The service reads data with the signed-in user's token, so Postgres row level security still applies. LLMs see only the minimum: titles and aggregates.
- **Numbers come from code, words from models.** LLMs phrase results; they never compute them.

## Architecture

```
React (Vercel) ──Supabase JWT──► ml-service (FastAPI, Python)
                                   ├─ /v1/categorize   user history match → TF-IDF + logistic regression
                                   ├─ /v1/insights     unusual spending · recurring payments · month-end forecast
                                   ├─ /v1/parse        rule-based slot filling → checked LLM fallback (LangChain)
                                   ├─ /v1/insights/summary  facts in code → LLM wording with placeholders
                                   ├─ /v1/help         hybrid search (BM25 + embeddings) → cited, checked answer
                                   ├─ /v1/assistant    LangGraph workflow: routing · tools · RAG · memory · human-in-the-loop
                                   └─ reads data through Supabase REST with the user's JWT (RLS applies)
```

## Roadmap

| # | Step | Techniques you can talk about | Status |
|---|---|---|---|
| 1 | Workflow setup | CI gates, branching, definition of done | done |
| 2 | [ML service foundation](02-ml-service.md) | FastAPI, JWT verification, config, testing, Docker | done |
| 3 | [Transaction categorizer](03-categorizer.md) | Text classification, TF-IDF, logistic regression, leakage-free evaluation, macro-F1, thresholds, calibration | done |
| 4 | [Spending insights](04-insights.md) | Evaluation by simulation, robust statistics vs percentile rules, Isolation Forest baseline, periodicity detection, forecasting with backtests, conformal calibration | done |
| 5 | [Natural-language quick add](05-quickadd.md) | Slot filling, rule-based extraction, entity-level evaluation, dev/test discipline | done |
| 6 | [LLM features](06-llm.md) | LangChain (LCEL, output parsers, fakes), provider abstraction, structured output, grounding by placeholders, fallbacks | done |
| 7 | [Help-center search (RAG)](07-rag.md) | Section chunking, BM25 from scratch, embeddings (bge-small, ONNX), hybrid search with RRF, declining off-topic questions, cited and checked answers | done |
| 8 | [The assistant (LangGraph)](08-assistant.md) | LangGraph state graphs, routing, tools, checkpointed memory, human-in-the-loop with interrupt/resume, per-user isolation | done |
| 9 | [MLOps](09-mlops.md) | Prometheus metrics, structured logs, a feedback loop with consent, champion/challenger retraining with a paired gate, an experiment log, free deployment | done |

Every step is done. Each page explains one step: the problem, the technique, how it was evaluated (with the numbers), the trade-offs, and the interview questions it answers.
