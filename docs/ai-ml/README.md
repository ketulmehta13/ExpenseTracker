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
                                   ├─ /v1/insights     anomalies · recurring payments · month-end forecast
                                   ├─ /v1/parse        rule-based extraction → LLM fallback (LangChain)
                                   ├─ /v1/assistant    LangGraph agent: tools · RAG · human-in-the-loop
                                   └─ reads data through Supabase REST with the user's JWT (RLS applies)
```

## Roadmap

| # | Step | Techniques you can talk about | Status |
|---|---|---|---|
| 1 | Workflow setup | CI gates, branching, definition of done | done |
| 2 | [ML service foundation](02-ml-service.md) | FastAPI, JWT verification, config, testing, Docker | done |
| 3 | [Transaction categorizer](03-categorizer.md) | Text classification, TF-IDF, logistic regression, leakage-free evaluation, macro-F1, thresholds, calibration | done |
| 4 | Spending insights | Robust z-score, Isolation Forest, periodicity detection, time-series forecasting and backtesting | next |
| 5 | Natural-language quick-add | Rule-based extraction, slot filling, entity-level evaluation | planned |
| 6 | LLM features | LangChain, structured output, provider abstraction, grounding and number verification | planned |
| 7 | RAG | Chunking, embeddings, vector search, retrieval with citations | planned |
| 8 | Finance assistant agent | LangGraph state machines, tool calling, routing, human-in-the-loop, memory | planned |
| 9 | MLOps | Experiment tracking, evaluation gates in CI, monitoring, retraining | planned |

Each step gets its own page in this folder when it lands.
