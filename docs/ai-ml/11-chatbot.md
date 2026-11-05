# 11. The RAG chatbot

A retrieval-augmented chatbot built with LangChain, FAISS and Groq. It answers from the app's help and finance articles and shows the sources it used. Questions about your own money are worked out by code from your transactions, and the model chooses which calculator to run through tool calling.

## How a message flows

```
React panel ──POST /chat/stream (Supabase token)──► FastAPI
  1. verify the token, apply the per-user rate limit
  2. secrets, other users' data, small talk: a reply decided in code, no model involved
  3. Groq chooses ONE tool, using the recent conversation (it sees no transactions):
       a calculator ─► code reads your rows with your token (RLS) and works out exact figures
       search_knowledge(standalone query) ─► step 4
       off_topic ─► a friendly reply
     If Groq fails or returns something invalid, backup rules decide instead
  4. FAISS: the 4 closest chunks ─► {context} ─► prompt ─► ChatGroq ─► StrOutputParser, streamed
     Figures + "why" or "what should I do": the figures come first, then this
  5. number check. Not in the articles, or it failed? ─► a general answer, labelled as such
  6. list only the sources the answer resembles, save the conversation (RLS)
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
| Choose a tool with LangChain tool calling; follow-ups become standalone queries | `app/chatbot/router.py` |
| Replies decided in code: security, profile, small talk | `app/chatbot/guardrails.py` |
| Nine calculators for your own money, and the backup rules | `app/chatbot/data_answers.py` |
| Saved conversations | `app/chatbot/history.py` |
| API, streaming, feedback | `app/routers/chat.py` |
| Panel | `frontend/src/components/ChatbotPanel.jsx`, `ChatBlocks.jsx`, `services/chatService.js` |

## Design decisions

- **FastEmbed instead of `sentence-transformers`.** It's the same `all-MiniLM-L6-v2` model on ONNX Runtime. `sentence-transformers` needs PyTorch, whose download alone is 514 MB, and the free server has 512 MB of memory. Measured locally, the service uses about 350 MB with the model and index loaded.
- **The index ships inside the Docker image.** Render's free disk is wiped on restart, so the build runs `training/build_index.py`. Changing a knowledge file means pushing and redeploying.
- **`openai/gpt-oss-120b`, not Llama 3.3.** Llama 3.3 wasn't available to this project's Groq key. `GROQ_MODEL` changes the model.
- **Transactions never go into FAISS.** Everyone shares the index. Calculators read your rows with your own token, so row level security applies, and sum them with `Decimal`, so figures are exact.
- **Tool calling instead of word lists.** The first version matched fixed words, so "earnings" and "debit" failed. The model now picks a tool, which handles typos and Hindi-English. Tools come from a fixed list, arguments are validated, none takes a user id, and the model never sees transactions. It costs one extra Groq call per message, and the rules remain as a backup.
- **Security replies in code.** Questions about passwords, system details and other users are answered before any model runs, so a clever prompt can't change the reply.
- **Labelled general answers.** Money topics the articles don't cover get an answer from the model's own knowledge, marked as general information. These can't be checked against a source.
- **Only the sources used.** Each retrieved passage is compared with the finished answer by embedding similarity. The closest is always listed, plus any close behind it, up to three.
- **The number check.** A prompt doesn't stop a model inventing a figure, so an answer with a number that isn't in the context or the question is replaced with "I don't know". This also rejects some correct answers that calculate a new number.

## Results

From [`reports/chatbot/report.md`](../../ml-service/reports/chatbot/report.md). Reproduce with `python -m training.evaluate_chatbot --gate` (in CI), or add `--llm` with `GROQ_API_KEY` set. Chunk size, overlap and k were chosen on dev questions only.

| Chunk size / overlap | Dev: right article first | Dev: right article retrieved (k = 4) |
|---|---|---|
| **500 / 100 (used)** | **0.924** | **1.000** |
| 500 / 200 | 0.924 | 1.000 |
| 1000 / 100 | 0.774 | 0.962 |
| 1000 / 200 | 0.774 | 0.962 |
| 1500 / 200 | 0.755 | 0.943 |

Going from k = 3 to 4 to 6 changed nothing at 500, so k stays at 4.

| On the test questions | Result |
|---|---|
| Right article first / retrieved (51 questions) | 0.902 / 0.941 |
| Routing with Groq (37 cases: real questions that failed, typos, Hindi-English) | 37 of 37 |
| The same cases with the backup rules alone | 27 of 37 (0.730) |
| Calculator figures against an independent sum | 400 of 400 exact |
| With Groq, answered from the articles | 45 of 51 (2 said "I don't know", 2 rejected by the number check, 2 rate limited) |
| With Groq, off-topic questions declined | 8 of 8 |
| Median time per answer with Groq | 2.05 s |

Results with Groq vary between runs, and the free tier sometimes rate-limits: in this project's runs, between 1 and 4 of the 59 questions were limited. The user then sees "I can't reach the AI service right now". In the app, questions the articles can't answer now also get a labelled general answer, which these counts don't include.

The test questions were written by the same person as the rules and the knowledge base is small (22 documents), so real users will find phrasings these sets miss. Several of the 37 routing cases are the exact questions the router was built to fix, so 37 of 37 shows those are fixed, not that every phrasing will work. "Answered" means the model's answer passed the number check, not that a person verified each one.

## Limits

- The chatbot can't add or change anything: use the forms, Quick Add or Scan bill.
- Vector search alone, with no keyword search, can miss exact terms.
- General answers aren't grounded in any source. They're labelled, but they can be wrong.
- Without Groq, the backup rules can't handle typos or Hindi-English (see the report).
- The number check catches invented figures, not invented words.

## Deployment

1. **Supabase:** run `supabase/migrations/20261105000000_rag_chatbot.sql` (chat history), then `20261106000000_chat_feedback.sql` (thumbs up or down), in the SQL editor. Both are safe to re-run. Without the second one, ratings just aren't saved.
2. **Render:** add `GROQ_API_KEY` as an environment variable. Until then it uses `LLM_API_KEY`, if `LLM_BASE_URL` points at Groq.
3. **Vercel:** nothing new, the panel uses `VITE_ML_API_URL`.

**Changing the knowledge:** add or edit a `.md`, `.txt` or `.pdf` file under `ml-service/knowledge/` and push. The next build re-creates the index.

**Rollback:** the previous chatbot is at the git tag `pre-rag-chatbot`.
