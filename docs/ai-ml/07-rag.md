# Step 7 — Help-center search (RAG)

**What it does:** answers questions about using the app ("how do I export to PDF?", "why was my payment marked unusual?", "export kaise kare") from a help center of 12 articles, with citations. Off-topic questions ("tell me a joke") are declined instead of guessed at. In [step 8](README.md#roadmap) the assistant uses it as one of its tools.

**Where it lives:**

| Piece | File |
|---|---|
| Help articles | [`ml-service/knowledge/`](../../ml-service/knowledge/) (Markdown) |
| Chunking | [`app/rag/knowledge.py`](../../ml-service/app/rag/knowledge.py) |
| Keyword search (BM25, from scratch) | [`app/rag/bm25.py`](../../ml-service/app/rag/bm25.py) |
| Embeddings | [`app/rag/embeddings.py`](../../ml-service/app/rag/embeddings.py) |
| Hybrid search and declining | [`app/rag/retriever.py`](../../ml-service/app/rag/retriever.py) |
| Answering with a grounding check | [`app/rag/answer.py`](../../ml-service/app/rag/answer.py) |
| API endpoint | [`app/routers/help.py`](../../ml-service/app/routers/help.py), `POST /v1/help` |
| Questions and evaluation | [`training/data/help_dev.jsonl`](../../ml-service/training/data/help_dev.jsonl), [`help_test.jsonl`](../../ml-service/training/data/help_test.jsonl), [`training/evaluate_rag.py`](../../ml-service/training/evaluate_rag.py) |
| Latest results | [`reports/rag/report.md`](../../ml-service/reports/rag/report.md) |

## Results at a glance (30 held-out test questions)

| Retriever, section chunks | Right article first (hit@1) | In the top three (hit@3) | MRR@5 |
|---|---|---|---|
| Keywords (BM25) | 0.733 | 0.867 | 0.817 |
| Embeddings (dense) | 0.867 | 0.967 | 0.918 |
| **Hybrid (shipped)** | **0.833** | **0.933** | **0.883** |

Off-topic questions: **90.9%** of test questions are correctly answered or declined.

## 1. RAG in one paragraph

Retrieval-augmented generation answers a question by first **retrieving** relevant passages from a knowledge base, then **generating** an answer from them, with citations. The model answers from text it was just shown rather than from memory, so it can quote facts it was never trained on (₹299 a month, a 15-minute sign-out), and the answer can be checked against its sources. Here the generation step is optional: without an LLM the answer is the opening of the best section, which is still correct and cited.

## 2. Chunking: follow the document's structure

Each article is split at its `##` headings, one chunk per section ("Exporting your data > Opening the CSV in Excel"), and the title and heading are prepended to the text that gets indexed.
- A section is a self-contained answer, so it can be cited exactly.
- The prefix gives a short section context that a bare paragraph lacks.

The common default, fixed windows of about 300 characters, was measured alongside. It loses on every retriever (hybrid hit@1: 0.767 vs 0.833 on test, 0.867 vs 0.967 on dev), because windows cut answers in half and mix topics.

## 3. Three retrievers

- **BM25 (keywords).** Written out in [`bm25.py`](../../ml-service/app/rag/bm25.py) to show the formula:
  - **IDF** rewards rare words ("pdf" over "my");
  - **term frequency saturates** (k1 = 1.5), so the tenth "category" adds little;
  - **length normalisation** (b = 0.75) stops long sections winning by size.

  It uses a small tokenizer: stopwords removed, plus a suffix stripper with Porter's consonant-undoubling rule, so "cancelling" matches "cancel". BM25 is exact and explainable, but it misses paraphrases. "I want to stop paying for pro" has no word in common with "Cancelling".
- **Dense (embeddings).** `BAAI/bge-small-en-v1.5` maps text to 384 numbers, so similar meanings land close together, measured by cosine similarity.
  - It runs on the CPU through ONNX Runtime ([fastembed](https://github.com/qdrant/fastembed)): about 70 MB, no PyTorch, no GPU, no API.
  - bge models expect an instruction in front of *queries* but not passages, so the two are embedded differently.
  - It finds paraphrases, but can blur specifics.
- **Hybrid.** Run both, and merge the two rankings with **Reciprocal Rank Fusion**: `score = Σ 1 / (60 + rank)`. RRF works on ranks, so a BM25 score of 12.3 and a cosine of 0.81 never need putting on one scale.

**Why no vector database?** 51 chunks × 384 floats is a NumPy matrix, and a search is one matrix-vector product, well under a millisecond. pgvector or FAISS start paying off at thousands to millions of chunks.

## 4. Declining what the help center can't answer

If the question's highest cosine similarity to any section is below **0.60**, the answer is "I couldn't find that in the help center", with no retrieval and no LLM call. The threshold was chosen on the dev questions:

| Threshold | 0.50 | 0.55 | **0.60** | 0.65 | 0.70 |
|---|---|---|---|---|---|
| Dev accuracy (answer in-scope, decline off-topic) | 0.909 | 0.970 | **1.000** | 0.939 | 0.879 |

On the test questions it scores **0.909**. The threshold belongs to the embedding model, so it's stored with the index: another model needs its own value.

## 5. Answers and the grounding check

- **No LLM:** the first two sentences of the best section, cited.
- **With an LLM** ([step 6](06-llm.md)'s provider): the top three sections are numbered `[1] [2] [3]`, and the model must answer in one to three sentences citing them. The answer is used only if:
  - it cites at least one source, and only sources it was given (`[7]` is rejected);
  - every number in it appears in a source it cites ("₹49 extra" is rejected when no source says 49);
  - it isn't too long.

  Otherwise the extractive answer is used. "I don't know" also falls back to the extractive answer, because retrieval had already passed the relevance threshold.

## 6. Evaluation done honestly

- **Two hand-written question sets.** Each question is labelled with the article(s) that answer it, and the sets include off-topic questions:
  - **dev** chose the chunking, the fusion and the decline threshold;
  - **test** was written at the same time and never used for a choice.
- **Article-level metrics.** An article counts once, at the rank of its best section:
  - hit@1 and hit@3;
  - MRR@5, the mean of 1/rank of the first right article.
- **What the test set said:**
  - Dense alone edged out hybrid by one question in 30 (0.867 vs 0.833 hit@1). The design was chosen on dev, where hybrid won, and one question is within the noise of a 30-question set. So hybrid stays, and the result is reported rather than hidden.
  - Two misses are about **content, not search**. The currency section sits in the privacy article, where nobody would look ("can I use dollars instead of rupees"). And no article says plainly that the Free plan hides transactions older than 3 months ("older transactions are missing"). Restructuring the help center fixes both, but that is left for a new round with fresh test questions, since doing it now would tune on the test set.
- **CI gate.** On the test set, hybrid hit@1 must stay at least 0.80, hit@3 at least 0.90 and decline accuracy at least 0.85.
- **Unit tests** use a deterministic word-hashing embedder, so they never download the model. The real model is exercised by the evaluation step, which CI caches.

## 7. Serving

- **The endpoint.** `POST /v1/help {question}` returns `{answer, source: llm | extractive | not_found, citations: [{article, title, section}]}` for signed-in users.
- **The index** is built on the first question, embedding all 51 sections in about a second, and reused afterwards.
- **The Docker build bakes in the embedding model**, so a new server never downloads it. If the model can't be loaded at all, search falls back to keywords alone.

## Reproduce

```bash
cd ml-service
python -m training.evaluate_rag --gate
```

## Interview questions this step answers

- *What is RAG, and why use it?* Retrieve, then generate from what was retrieved, with citations: current facts, checkable answers, and nothing to fine-tune.
- *How did you chunk documents?* By section, with title and heading prefixes, and it measurably beat fixed windows.
- *BM25 or embeddings?* Both: BM25 is exact on terms like "PDF", embeddings handle paraphrases, and RRF fuses them without score calibration. I'd also show the numbers, including where dense alone came out slightly ahead.
- *How do you evaluate retrieval?* Labelled questions, hit@k and MRR at the right granularity (articles), a dev/test split, and comparison with baselines.
- *How do you stop the bot answering things it shouldn't?* A similarity threshold chosen on dev questions, with off-topic examples in both sets.
- *How do you keep generated answers grounded?* Citations to numbered sources, and every number checked against the sources cited, with an extractive fallback.
- *When do you need a vector database?* Not for 51 chunks. At scale: pgvector next to the data, or FAISS/HNSW for approximate nearest-neighbour search.
