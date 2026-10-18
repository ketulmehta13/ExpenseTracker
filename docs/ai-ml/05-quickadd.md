# Step 5 — Natural-language quick add

**What it does:** the user types one line, such as "swiggy 450 yesterday", "₹2,499 amazon headphones" or "salary credited 92k on 1st". The transaction form opens pre-filled with the title, amount, date, type and a suggested category. Nothing is saved until the user taps Save.

**Where it lives:**

| Piece | File |
|---|---|
| Parser | [`ml-service/app/nlp/quickadd.py`](../../ml-service/app/nlp/quickadd.py) |
| API endpoint | [`ml-service/app/routers/parse.py`](../../ml-service/app/routers/parse.py) |
| Labelled sentences | [`training/data/quickadd_dev.jsonl`](../../ml-service/training/data/quickadd_dev.jsonl), [`training/data/quickadd_test.jsonl`](../../ml-service/training/data/quickadd_test.jsonl) |
| Evaluation and gate | [`training/evaluate_quickadd.py`](../../ml-service/training/evaluate_quickadd.py) |
| Latest results | [`reports/quickadd/report.md`](../../ml-service/reports/quickadd/report.md) |
| Frontend | [`QuickAdd.jsx`](../../frontend/src/components/QuickAdd.jsx), [`services/mlService.js`](../../frontend/src/services/mlService.js) |

## Results at a glance (80 held-out test sentences)

| Field | Naive baseline | Rules |
|---|---|---|
| Amount | 63.7% | **100%** |
| Date | 60.0% | **97.5%** |
| Type (income or expense) | 86.2% | **98.8%** |
| Title, token F1 | 69.7% | **98.2%** |
| Whole entry right | 20.0% | **95.0%** |
| Category (categorizer on the parsed title) | 85.1% | **91.9%** |

## 1. Framing: slot filling

This is **information extraction**: fill four slots (amount, date, type, title) from a short, informal sentence. Chatbots call it slot filling, and the NER-style name is entity extraction.

The slots behave very differently:
- Amounts and dates have rigid surface forms (₹1,25,000, 1.5k, 12/10, "3rd oct").
- Type depends on cue words.
- The title is "whatever is left".

So each slot gets its own extractor, run in a fixed order.

## 2. Why rules, not a model

| Option | Verdict |
|---|---|
| **Rules (chosen)** | No labelled data needed. Every decision can be explained and unit-tested. Microsecond latency. Perfect on rigid formats. |
| CRF or spaCy NER | Needs hundreds of token-labelled sentences. Learns the same patterns less reliably for numbers and dates. |
| LLM | Handles anything, but it is slow, costs per call, can invent a number, and needs its output checked anyway. In this project it becomes the **fallback** for what the rules miss (step 6). |

**Rules first, model or LLM for the long tail** is a common production pattern. Rules give a measurable, cheap baseline, and the failure list shows exactly where a model would earn its keep.

## 3. How the parser works

Each extractor removes what it matched before the next one looks. A number used in "1st oct" can never also become the amount.

1. **Date.**
   - Relative words: today, yesterday, kal, aaj, parso, "day before yesterday", "2 days ago", "a week ago".
   - Weekdays: "friday" means the most recent Friday, and "last sunday" on a Sunday means a week ago.
   - Explicit dates: "3rd oct", "oct 3", "2026-09-30", plus numeric dates, which are **day-first** as written in India ("12/10" is 12 October).
   - A date with no year resolves to the **most recent past** one, because expenses have already happened: "25 dec" in October means last December.
   - A "year" that isn't plausible is left alone, so in "insurance 5 sep 2000" the 2000 stays the amount.
2. **Amount.**
   - Formats: Indian digit grouping (1,25,000), decimals, k / lakh / crore, and currency markers (₹, rs, inr, /-).
   - Digits inside words are ignored (1mg, zee5).
   - With several numbers, a currency-marked one wins, then the largest: "2 coffees 300" gives 300.
3. **Type.**
   - Income cue words: received, credited, salary, refund, cashback, dividend…
   - "got … from" counts as income.
   - A cue preceded by a payee role is an expense: "maid salary" is money paid out.
   - Everything else is an expense, the common case.
4. **Title.** The remaining words, minus filler at the edges: "paid … for", "spent … on", "received". Inner words stay, so "uber 340 to office" gives "Uber to office" and "iphone 15 79900" keeps "Iphone 15".

The response also says **which slots came from the text and which were defaults** (`found`). That way the app can show the user what it assumed.

## 4. Evaluation done honestly

- **Two hand-written sets**, relative to a fixed "today" (Sunday 18 October 2026):
  - **Dev (99 sentences):** written alongside the rules. Its 100% score proves only that the rules do what I wrote them to do.
  - **Test (80 sentences):** written **before** the parser and never used to change it. Its 95% is the honest number.
- **Entity-level scoring.** Each slot is scored on its own. Amount, date and type use exact match. The title uses **token-level F1** (as in SQuAD), so "Groceries dmart" against "Groceries at dmart" earns partial credit instead of a flat fail.
- **A naive baseline.** First number as the amount, today as the date, always an expense. It gets only **20%** of entries fully right: "₹2,499" becomes 2, every "yesterday" is wrong, and every salary is an expense.
- **Every test failure is listed** in the report. All four are phrasings the rules have never seen: "kal raat" (Hinglish for "last night"), "3 days back", "last night" and "got paid". They're deliberately left unfixed: patching them now would be tuning on the test set. They become dev examples for the next iteration and are exactly what the LLM fallback in step 6 is for.
- **End-to-end category.** The categorizer, run on the *parsed* title, picks the right category 91.9% of the time. Extraction errors would show up here as a drop, so this also checks that the two components work together.

## 5. Serving

- **Endpoint.** `POST /v1/parse {text, today}` returns the draft, plus a category from the **same cascade as `/v1/categorize`**: the user's history first, then the model. The cascade is one shared function, so the two endpoints can't drift apart.
- **The client sends its local date**, since "yesterday" depends on it. The server rejects dates more than a day from its own.
- **The frontend's Quick Add bar** uses the ML service when `VITE_ML_API_URL` is set, and the LLM proxy otherwise. Both paths open the same pre-filled form.

## 6. MLOps

- **CI gate.** `python -m training.evaluate_quickadd --gate` fails the build if test-set accuracy drops below 95% for amount, 90% for date or type, or 85% title F1. The floors were fixed **before** the first test run.
- **Report.** The run writes [`reports/quickadd/report.md`](../../ml-service/reports/quickadd/report.md), including the full failure list, and CI uploads it as an artifact.

## Reproduce

```bash
cd ml-service
python -m training.evaluate_quickadd --gate
```

## Interview questions this step answers

- *How would you extract structured fields from free text?* Slot filling with per-slot extractors, in an order that prevents double use of the same token.
- *Rules or ML?* Rules where the formats are rigid and labels are scarce. Measure them, then use the failure list to decide where a model or LLM pays off.
- *How do you evaluate an extractor?* Per-entity exact match, token-level F1 for free-text spans, whole-record accuracy, and a naive baseline.
- *How do you keep evaluation honest when you write the rules yourself?* A test set written first and never used for changes, floors fixed before the first test run, and every failure published.
- *What locale problems did you handle?* Day-first dates, lakh/crore and 1,25,000 grouping, the ₹ and /- markers, Hinglish words (kal, aaj, parso), and past-biased year inference.
- *What's next?* An LLM fallback with schema-validated output, used only when the rules miss a slot (step 6). Then turn its corrections into new dev examples.
