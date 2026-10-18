# Step 8 — The assistant (LangGraph)

**What it does:** a chat panel, opened from the round button in the corner of every page. It covers:
- **Your money:** "how much did I spend on food last month?", "and this month?", "where did most of my money go?", "am I on track with my budget?", "what subscriptions do I have?", "anything unusual?".
- **The app:** "how do I export to PDF?", answered by the help center from [step 7](07-rag.md).
- **Adding:** "add 450 swiggy yesterday" shows a draft, and nothing is saved until you tap **Save**.

**Where it lives:**

| Piece | File |
|---|---|
| Understanding (intents, slots, follow-ups) | [`ml-service/app/assistant/router.py`](../../ml-service/app/assistant/router.py) |
| Tools and replies | [`ml-service/app/assistant/tools.py`](../../ml-service/app/assistant/tools.py) |
| The LangGraph graph | [`ml-service/app/assistant/graph.py`](../../ml-service/app/assistant/graph.py) |
| API | [`ml-service/app/routers/assistant.py`](../../ml-service/app/routers/assistant.py): `POST /v1/assistant/chat`, `POST /v1/assistant/confirm` |
| Evaluation | [`training/evaluate_assistant.py`](../../ml-service/training/evaluate_assistant.py), with [`assistant_dev.jsonl`](../../ml-service/training/data/assistant_dev.jsonl) and [`assistant_test.jsonl`](../../ml-service/training/data/assistant_test.jsonl) |
| Chat panel | [`AssistantPanel.jsx`](../../frontend/src/components/AssistantPanel.jsx) |

## 1. Workflow, not a free-running agent

An "agent" can mean an LLM in a loop, choosing tools until it decides it's done. For a finance app that's the wrong default:
- answers must be exact and repeatable;
- every step should be explainable;
- nothing should change your data unless you asked.

So the assistant is a **workflow with explicit routing**, the pattern often recommended before reaching for autonomy:

```
START → understand → spending | breakdown | budget | subscriptions | unusual | help | greeting → END
                   → add (draft) → confirm  ⏸ waits for the user → save → END
```

- **Understand once.**
  - Ordered rules pick the intent.
  - Questions about the app ("what does unusual spending mean?", "how is the forecast calculated?") are checked before data intents, because they use the same words.
  - Slots come from the same message:
    - **period:** "last month", "in September", "this week" (from Monday), "pichle mahine";
    - **one of your categories:** directly, or through aliases, so "groceries" means your Food;
    - **a merchant from your own history:** "swiggy".
- **An LLM only for the long tail.** If the rules don't recognise the phrasing and an LLM is configured, it chooses the intent (structured output validated against the intent list). The slots still come from rules. With no LLM, unrecognised messages go to the help center, which can decline them.
- **One tool per message.** Tools are plain functions over your data, and every number in a reply is computed and written by a template, as in [step 6](06-llm.md).

## 2. LangGraph concepts used

| Concept | Here |
|---|---|
| `StateGraph` with a typed state | `AssistantState`: the message, the latest understanding, the reply, citations, a draft |
| Nodes and conditional edges | `understand`, then routing on `state["understanding"]["intent"]` to one node per intent |
| Checkpointer (`InMemorySaver`) | The state is saved per **thread**, which gives memory and resumable pauses |
| `interrupt()` and `Command(resume=…)` | Human-in-the-loop: the confirm node pauses with the draft, and the next request resumes it with your answer |
| Run config | Per-request objects (your data, today's date, the models) travel in `config["configurable"]`, never in the checkpoint |

### Memory: follow-ups
The checkpointed state keeps the last understanding:
- "how much did I spend on food last month?" then "**and this month?**" keeps Food and changes the period;
- "**what about shopping?**" replaces the category and keeps the period.

A new filter replaces the old one; anything not mentioned is carried over.

### Human-in-the-loop: nothing is saved without you
1. **Draft.** "add 450 swiggy yesterday" goes to the draft node. The command word is removed, the [step 5](05-quickadd.md) parser fills the fields (with the [step 6](06-llm.md) LLM fallback when unsure), and the [step 3](03-categorizer.md) cascade suggests a category from your own history.
2. **Pause.** The confirm node calls `interrupt({"draft": …})`. The graph stops, its state is checkpointed, and the API returns the draft.
3. **Resume.** `POST /v1/assistant/confirm {approve}` resumes the graph from that exact point:
   - *approve* saves the transaction **with your own token**, so row level security applies to the write too. It then clears the cached insights, so the next answer includes the new transaction.
   - *cancel* saves nothing.
4. **An unanswered draft.** Sending a new message instead of answering counts as cancel.

### Isolation
Threads are keyed by **your verified user id plus the client's thread id**. Another user who sends the same thread id gets a different thread, so they can't see or resume your conversation. A test proves it.

## 3. Evaluation

- **Labelled messages:** 41 dev and 33 test examples, written before the router, with the intent and, for data questions, the period, category and merchant. They include short conversations (follow-ups) and deliberate traps (definitions using data words).
- **Metrics:**
  - intent accuracy;
  - data questions with every slot right;
  - follow-ups understood.
- **CI gate.** On the test set, intent accuracy must stay at least 0.90 and slot accuracy at least 0.85.

| | Dev | Test |
|---|---|---|
| Intent accuracy | 1.000 | 1.000 |
| Every slot right on data questions | 1.000 | 1.000 |
| Follow-ups understood | 1.000 | 1.000 |

**Read the perfect test score with care.** The test set was never used to change the rules, but the same person wrote both sets and the rules, so it mostly shows the rules cover that person's phrasing. Real users will say things neither set contains, and the LLM fallback is there for exactly that. The next step ([step 9](README.md#roadmap)) logs unrecognised messages, because they're the real test set.

- **Exact numbers** are tested separately:
  - the spending and breakdown tools are checked against a direct computation on a simulated user;
  - the full chat flow runs through the API against a fake Supabase: exact totals, follow-up memory, draft, confirm and save, cancel, auto-cancel and per-user isolation.

## 4. Serving

- **`POST /v1/assistant/chat {message, thread_id?, today}`** returns `{thread_id, intent, reply, citations, pending, saved}`.
- **`POST /v1/assistant/confirm {thread_id, approve}`** resumes a paused draft. It returns 409 if nothing is waiting.
- **Memory is in-process (`InMemorySaver`).** That's fine for one server. Several instances need a shared checkpointer (Postgres or Redis), and a restart forgets open conversations.
- **The chat panel** is portaled to `<body>`, works full-screen on phones, and fires the app's `transaction-updated` event after a save, so the open page refreshes.

## Interview questions this step answers

- *Agent or workflow?* A workflow with explicit routing: predictable, testable and auditable. An LLM is used only where rules can't cope, and actions need human approval.
- *What is LangGraph for?* Stateful graphs: typed state, conditional routing, checkpointed memory, and `interrupt`/resume for human-in-the-loop.
- *How does the assistant remember context?* A checkpointer saves the graph state per thread, so follow-ups reuse the previous intent and slots.
- *How do you keep an assistant from doing something harmful?* It reads with the user's token. Writes happen only after explicit confirmation, also with the user's token, so row level security applies. Threads are isolated per user.
- *How do you evaluate a conversational system?* Labelled single messages and conversations: intent and slot accuracy, plus follow-ups. Separately, exact-number tests on the tools and end-to-end tests of the flows. Then log production misses.
- *What would you add?* A shared checkpointer, streaming replies, more tools (budgets per category), and an LLM that writes answers with placeholders, as in step 6.
