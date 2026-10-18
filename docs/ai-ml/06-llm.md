# Step 6 — LLM features with LangChain

**What it does:** two features use a large language model, and both work without one.

1. **Quick-add fallback.** When the rules from [step 5](05-quickadd.md) look unsure, the LLM gets a turn. "ola 250 3 days back" becomes "Ola · ₹250 · 15 Oct" instead of the title "Ola 3 days back" dated today.
2. **Monthly summary.** Two or three sentences above the dashboard cards, for example: "You've spent ₹10,422 so far in October, ₹1,222 more than at this point last month…". Every number in it is computed and inserted by code, never written by the model.

**Where it lives:**

| Piece | File |
|---|---|
| Provider switch | [`ml-service/app/llm/provider.py`](../../ml-service/app/llm/provider.py) |
| Quick-add fallback | [`ml-service/app/llm/extract.py`](../../ml-service/app/llm/extract.py), used by [`routers/parse.py`](../../ml-service/app/routers/parse.py) |
| Monthly summary | [`ml-service/app/llm/summary.py`](../../ml-service/app/llm/summary.py), served at `GET /v1/insights/summary` |
| Grounding check | [`ml-service/app/llm/verify.py`](../../ml-service/app/llm/verify.py) |
| Tests (fake models, adversarial cases) | [`tests/test_llm.py`](../../ml-service/tests/test_llm.py) |
| Evaluation with a real model | [`training/evaluate_llm.py`](../../ml-service/training/evaluate_llm.py) |

## Principles

- **Free and provider-agnostic.** LangChain's chat-model interface hides the vendor. The model is set by configuration:
  - `ollama`: a local model such as `qwen2.5:3b`;
  - `openai`: any OpenAI-compatible endpoint, including free hosted tiers;
  - `none`.

  No paid API is required.
- **Optional by design.** With `LLM_PROVIDER=none`, quick add uses rules alone and the summary uses a template. Every LLM failure (timeout, server down, malformed output) falls back the same way. The model can improve a feature, but no feature depends on it.
- **Numbers come from code, words from models.** The model never computes a figure, and anything it writes is checked before a user sees it.
- **The user stays in charge.** Quick add only pre-fills a form, and the response says which fields the LLM filled, so the app can ask the user to check them.

## LangChain, as used here

| Concept | Where |
|---|---|
| `BaseChatModel`: one interface for Ollama, OpenAI-compatible APIs and fakes | `provider.py` |
| `ChatPromptTemplate` with system and human messages | both features |
| LCEL composition: `prompt | model | parser` is a `Runnable` with `invoke` / `ainvoke` | both features |
| `PydanticOutputParser`: schema to format instructions, reply to a validated object | `extract.py` (`LLMDraft`) |
| `StrOutputParser` | `summary.py` |
| `FakeListChatModel`, `RunnableLambda`: deterministic tests, slow or broken models | `tests/test_llm.py` |

**Why a parser rather than `with_structured_output`?** Native structured output relies on tool-calling or JSON-schema support. Many small local models and every fake lack it. Format instructions plus a Pydantic parser work with any chat model, and a validation failure is handled like any other failure: the rules' answer stands.

## 1. Quick-add fallback

- **When it runs.** Only when the rules look unsure: no amount found, or time words left in the title ("back", "night", "raat"…). Confident parses never pay the LLM's latency. A test fails if the model is called for "swiggy 450".
- **What it returns.** `LLMDraft {title, amount, date, type}` from a prompt that gives today's date and weekday, explains Hindi time words, and asks for JSON only.
- **What is checked before use:**

  | Field | Check |
  |---|---|
  | Amount | Must be one of the numbers actually written in the note, so a model can't invent ₹999 |
  | Title | May only use words from the note |
  | Date | Must fall within the past year. That is plausibility only: "3 days back" can't be verified the way "250" can. This is why the app shows which fields the LLM filled (`llm_filled`) and asks the user to check them |
  | Type | Accepted when the rules found no cue |

- **How results merge.** Rules keep every slot they found, and checked LLM values fill only the gaps.

## 2. Monthly summary, and why the model never writes numbers

**Facts are computed in code:**
- spending so far against the same point last month;
- the month-end projection and the budget;
- the biggest category;
- the largest unusual payment;
- subscriptions.

A **template** sentence always exists. An LLM may only reword it.

**Version 1 checked numbers.** The model saw the facts and wrote a summary. Every number in it had to be within 1% of a fact, otherwise the template was used. Its own evaluation found a flaw. Across 30 simulated users' real months, a wrong figure was planted into each honest summary. **Two of 30 passed**: each planted figure happened to land within 1% of a *different* fact (last month's spending). Number checking proves a number is *a* fact, not that it is attached to the *right* words.

**Version 2 (shipped) uses placeholders.**
- The model never sees or writes a number. The facts arrive as `Spent so far this month: [spent]`, and the model writes "You've spent [spent] so far…".
- Code substitutes each placeholder with the value it computed.
- The text is rejected, and the template used, if it:
  - writes **any digit itself** (except inside a known name such as "Tata 1mg");
  - uses a placeholder that doesn't exist;
  - runs too long.
- The template goes through the same substitution, so honest text and model text share one path.

**The guardrail's evaluation**, a test that runs in CI, uses 30 simulated users' real months:
- every honest summary is accepted;
- every tampered one is rejected: 90 of 90 (a planted percentage, a planted amount and an unknown placeholder per user).

**The residual risk, stated plainly.** A model could put a real placeholder in the wrong sentence, for example `[projected]` where it means money already spent. Meaningful placeholder names, one-meaning-per-line facts and short outputs make that unlikely, but not impossible.

**Serving.** `GET /v1/insights/summary` returns `{text, source: "llm" | "template"}`. The summary is cached while its facts are unchanged, because a local model takes seconds. The dashboard shows "Written by AI · every number computed and checked by the app" only when the model's text was used.

## Testing without an LLM

CI has no model server, so every behaviour is tested with LangChain's fake chat models and `RunnableLambda` stand-ins:
- structured output is parsed into `LLMDraft`;
- unusable replies (prose, missing fields, empty) are ignored;
- a slow model is abandoned at the timeout;
- an invented amount is rejected;
- a draft fills only the gaps;
- a summary with its own digits or unknown placeholders is replaced by the template;
- a broken model gives the template;
- summaries are cached;
- the provider switch works, and the API key never appears in `repr`.

## Evaluating with a real model

```bash
cd ml-service
ollama pull qwen2.5:3b                       # or any OpenAI-compatible free endpoint
LLM_PROVIDER=ollama LLM_MODEL=qwen2.5:3b python -m training.evaluate_llm
```

It reports:
- the quick-add test set with rules alone and with the LLM fallback;
- for simulated users, how often the model's summary passes the placeholder check, and the median latency.

It writes `reports/llm/metrics.json`. A rejected summary falls back to the template, so this measures quality, not safety.

**Not run yet:** this machine has no local model installed, and real-model numbers will be added when one is.

## Privacy

- The quick-add prompt contains only the one-line note the user typed.
- The summary prompt contains aggregates, a category name and one merchant title. No transaction list is sent to the model.
- `LLM_API_KEY` is excluded from the settings' `repr`, so it can't leak into logs or tracebacks.

## Interview questions this step answers

- *How do you stop an LLM from hallucinating numbers?* Don't let it write any. It uses placeholders that code fills, and any digit of its own rejects the output. I started with number verification and my own test found its blind spot: a wrong number that matches a different fact.
- *How do you make LLM features reliable?* Make them optional: timeouts, schema validation, field-level checks against the input, and a deterministic fallback for every failure.
- *How do you get structured output from small local models?* Format instructions plus a Pydantic parser. Validation failures go down the same path as any other failure.
- *How do you test LLM code in CI?* Fake chat models for the happy path, plus adversarial replies: prose, broken JSON, invented values, slow and broken models.
- *Why LangChain?* A provider-neutral chat-model interface, composable prompt-model-parser chains, output parsers and test fakes. It's also the base for the agent in step 8.
- *When should an LLM not be used?* When rules are already right and fast: quick add calls the model only when the rules look unsure.
