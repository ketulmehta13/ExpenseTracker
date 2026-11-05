# 11. The RAG chatbot

A retrieval-augmented chatbot built with LangChain, FAISS and Groq. It answers from the app's help and finance articles and shows its sources. Questions about your own money are worked out by code from your transactions.

## How a message flows

```
React panel ──POST /chat/stream (Supabase token)──► FastAPI
  1. verify the token, apply the per-user rate limit
  2. a follow-up?  history + Groq ─► a standalone question
  3. about your own money?  calculators, reading with your token (RLS) ─► exact figures
     (figures only: done. Figures + "why" or "what should I do": continue, and put the figures first)
  4. FAISS: the 4 closest chunks ─► joined into {context}
  5. prompt ─► ChatGroq ─► StrOutputParser, streamed to the panel
  6. number check, sources, conversation saved in Supabase (RLS)
```

## The chain

```python
chain = {"context": retriever | format_docs, "question": RunnablePassthrough()} | PROMPT | llm | StrOutputParser()
```

The prompt says to answer only from the context and to say "I don't know" otherwise.

| Step | Where |
|---|---|
| Load Markdown, text and PDF files into `Document`s | `app/chatbot/index.py` |
| Split with `RecursiveCharacterTextSplitter` | `app/chatbot/index.py` |
| Embed with MiniLM, store in FAISS, save and reload | `app/chatbot/index.py`, `training/build_index.py` |
| Prompt, `ChatGroq`, `format_docs`, the chain, the number check | `app/chatbot/chain.py` |
| Rewrite follow-ups into standalone questions | `app/chatbot/rewrite.py` |
| Calculators for your own money | `app/chatbot/data_answers.py` |
| Saved conversations | `app/chatbot/history.py` |
| API, streaming | `app/routers/chat.py` |
| Panel | `frontend/src/components/ChatbotPanel.jsx`, `services/chatService.js` |

## Design decisions

- **FastEmbed instead of `sentence-transformers`.** It's the same `all-MiniLM-L6-v2` model on ONNX Runtime. `sentence-transformers` needs PyTorch, whose download alone is 514 MB, and the free server has 512 MB of memory. Measured locally, the service uses about 350 MB with the model and index loaded.
- **The index ships inside the Docker image.** Render's free disk is wiped on restart, so the build runs `training/build_index.py`. Changing a knowledge file means pushing and redeploying.
- **`openai/gpt-oss-120b`, not Llama 3.3.** Llama 3.3 wasn't available to this project's Groq key. `GROQ_MODEL` changes the model.
- **Transactions never go into FAISS.** Everyone shares the index. Calculators read your rows with your own token, so row level security applies, and sum them with `Decimal`, so figures are exact.
- **The number check.** A prompt doesn't stop a model inventing a figure, so an answer with a number that isn't in the context or the question is replaced with "I don't know". This also rejects some correct answers that calculate a new number.

## Results

From [`reports/chatbot/report.md`](../../ml-service/reports/chatbot/report.md). Reproduce with `python -m training.evaluate_chatbot --gate` (in CI), or add `--llm` with `GROQ_API_KEY` set. Chunk size, overlap and k were chosen on dev questions only.

| Chunk size / overlap | Dev: right article first | Dev: right article retrieved (k = 4) |
|---|---|---|
| **500 / 100 (used)** | **0.924** | **1.000** |
| 500 / 200 | 0.924 | 1.000 |
| 1000 / 100 | 0.736 | 0.962 |
| 1000 / 200 | 0.736 | 0.962 |
| 1500 / 200 | 0.736 | 0.962 |

Going from k = 3 to 4 to 6 changed nothing at 500, so k stays at 4.

| On the held-out test questions | Result |
|---|---|
| Right article first / retrieved (51 questions) | 0.922 / 0.961 |
| Routing to calculators (27 messages) | 0.963 |
| Calculator figures against an independent sum | 400 of 400 exact |
| With Groq, answerable questions answered | 42 of 51 (2 said "I don't know", 3 rejected by the number check, 4 rate limited) |
| With Groq, off-topic questions declined | 8 of 8 |
| Median time per answer with Groq | 0.94 s |

Results with Groq vary between runs: an earlier run answered 46 of 51 with 1 rate limited. The rate limits came from asking 59 questions in a few minutes on Groq's free tier, and a busy day on the real site could hit them too. The user then sees "I can't reach the AI service right now".

The test questions were written by the same person as the rules, and the knowledge base is small (22 documents), so real users will find phrasings these sets miss. The reported "answered" counts mean the model gave an answer that passed the number check, not that a person verified each one.

## Limits

- The chatbot can't add or change anything: use the forms, Quick Add or Scan bill.
- Vector search alone, with no keyword search, can miss exact terms.
- Answers about your own money cover spending, income, categories, comparisons and the budget. Other questions go to the documents, and usually get "I don't know".
- Off-topic questions rely on the model following the prompt. The number check catches invented figures, not invented words.

## Deployment

1. **Supabase:** run `supabase/migrations/20261105000000_rag_chatbot.sql` in the SQL editor. It's safe to re-run. It removes the old knowledge and action tables and creates the chat history tables. Until then the chatbot answers but doesn't save conversations.
2. **Render:** add `GROQ_API_KEY` as an environment variable. Until then it uses `LLM_API_KEY`, if `LLM_BASE_URL` points at Groq.
3. **Vercel:** nothing new, the panel uses `VITE_ML_API_URL`.

**Changing the knowledge:** add or edit a `.md`, `.txt` or `.pdf` file under `ml-service/knowledge/` and push. The next build re-creates the index.

**Rollback:** the previous chatbot is at the git tag `pre-rag-chatbot`.
