# Step 9 — MLOps: monitoring, feedback, retraining, deployment

**What it does:** closes the loop around steps 3–8.
- **Monitoring:** Prometheus metrics and structured logs.
- **Feedback:** every category suggestion's fate (accepted or overridden) is recorded.
- **Retraining:** a champion/challenger job that learns from opted-in users' feedback and promotes only if nothing gets worse.
- **Experiment log:** every training and evaluation run is recorded.
- **Deployment:** a blueprint that puts the service online for free.

**Where it lives:**

| Piece | File |
|---|---|
| Metrics and JSON logs | [`ml-service/app/observability.py`](../../ml-service/app/observability.py), served at `GET /metrics` |
| Feedback table, RLS, quality view | [`supabase/migrations/20261018000000_ml_feedback.sql`](../../supabase/migrations/20261018000000_ml_feedback.sql) |
| Feedback from the form, opt-in toggle | [`TransactionModal.jsx`](../../frontend/src/components/TransactionModal.jsx), [`Profile.jsx`](../../frontend/src/pages/Profile.jsx) |
| Retraining | [`training/retrain_categorizer.py`](../../ml-service/training/retrain_categorizer.py), [`.github/workflows/retrain.yml`](../../.github/workflows/retrain.yml) |
| Experiment log | [`training/runs.py`](../../ml-service/training/runs.py) |
| Deployment | [`render.yaml`](../../render.yaml) |

## 1. The lifecycle, end to end

```
 data ──► train ──► evaluate ──► gate in CI ──► image (model inside) ──► serve
  ▲                                                                       │
  │       champion / challenger ◄── opted-in feedback ◄── accepted? overridden? ◄─┘
  └────────── human review ◄────── report ◄──────────────┘
```

What runs where:

| Stage | How |
|---|---|
| Reproducible training | Fixed seeds. The version is the date plus a hash of the data and parameters. A model card is written on every run. |
| Evaluation gates in CI | Five gates fail the build: categorizer holdout macro-F1, insight detectors, quick-add test set, RAG retrieval, assistant routing. |
| Serving artefacts | The categorizer is trained, and the embedding model baked, **inside** the Docker image, so they always match the installed libraries. |
| Monitoring | `/metrics` for Prometheus; JSON logs to stdout. |
| Feedback | An `ml_feedback` row each time a suggested category is saved or overridden. |
| Retraining | A weekly job (off until configured) produces a challenger and a promotion decision. A person deploys it. |

## 2. Monitoring

**Metrics** (`GET /metrics`, Prometheus text format; set `METRICS_TOKEN` to require a bearer token):

| Metric | What it tells you |
|---|---|
| `ml_requests_total{route, status}` | Traffic and errors per endpoint |
| `ml_request_seconds{route}` (histogram) | Latency percentiles per endpoint |
| `ml_feature_events_total{feature, outcome}` | What each feature did, listed below |

The `ml_feature_events_total` outcomes:
- categorize: history / model / none;
- help: llm / extractive / not_found;
- summary: llm / template;
- parse: rules / rules+llm;
- the assistant's intents;
- saved vs cancelled drafts.

Routes are labelled by their **template** (`/v1/insights`), never the raw URL: query strings and ids would create unlimited label values ("high cardinality"), which is the classic way to break Prometheus.

**What to watch, and what it means:**
- **Model suggestions falling while "none" rises:** users are typing things the model doesn't know. That's data drift, so retrain.
- **More `help → not_found`:** questions the help center doesn't cover. Write articles.
- **`summary → template` while an LLM is configured:** the model keeps failing the placeholder check. Check the model.

**Logs** are one JSON object per line (time, level, logger, message), with no user text. A log platform can index them without parsing.

## 3. Feedback: did the suggestion help?

The transaction form remembers the last ML suggestion it showed. On save it inserts an `ml_feedback` row:
- the title, amount and type;
- where the suggestion came from, and its label, confidence and model version;
- the category actually saved;
- **accepted**, compared by name, so a suggestion the user created as a new category still counts.

The insert is best-effort and never blocks or breaks saving.

The table is designed like an audit log:
- **Append-only.** Users can insert and read their own rows; `UPDATE` and `DELETE` are revoked.
- **Owned.** `user_id` defaults to `auth.uid()`, and row level security rejects rows for anyone else.
- **Gone with the account.** It cascades on account deletion.
- **`ml_suggestion_quality`.** A `security_invoker` view gives the weekly acceptance rate by source: users see only their own rows, and the dashboard (service role) sees everyone's.

All of this is checked by the migration tests in CI (PGlite): owner-only, append-only, the view's visibility, and cascade on delete.

**Consent.** Settings has "Help improve category suggestions", **off by default**. Feedback from users who haven't opted in is still useful for monitoring (the acceptance rate) but is never used for training.

## 4. Retraining: champion and challenger

`python -m training.retrain_categorizer --from-supabase` (or `--feedback file.csv`):

1. **Export.** Reads feedback only from opted-in users, with the service role. The job runs outside the app.
2. **Label.** Maps each saved category onto the canonical labels through the app's aliases. Custom categories ("Pets") can't be mapped and are dropped.
3. **Hold out.** Keeps a fifth of the feedback aside.
4. **Train.** The **challenger** is the champion's pipeline retrained on synthetic data plus the feedback. Feedback rows are weighted up, but capped at **a fifth of the training weight**.
5. **Compare** on the same data:
   - the challenger must be **better on held-out feedback**;
   - and **no worse on the hand-written holdout**: the examples it newly gets wrong, minus those it newly gets right, must be at most 2.
6. **Report.** The decision goes to a report. A promoted model is saved next to it, and **a person deploys it**: feedback is small at first, and model files are pickles, i.e. code.

### Two lessons the tests taught

- **Cap the feedback weight.** A fixed 5× weight let 160 feedback rows from four merchants outweigh a small synthetic base. The challenger was perfect on feedback and 7 points worse on the holdout, and the gate rejected it. Capping feedback at a fifth of the weight fixed the cause.
- **Compare classifiers in pairs, not by a metric difference.** The first rule ("macro-F1 within 0.01") rejected a harmless challenger. On 142 examples one example moves macro-F1 by about a point, and the "drop" was **one** net example: four newly wrong, three newly right. Counting disagreements on the same examples, the idea behind McNemar's test, measures the real difference.

### The guardrails, tested both ways

- **Promoted:** feedback about merchants the model has never seen (Dunzo → Food, Cleartrip → Travel). Accuracy on held-out feedback rises sharply, and the holdout is unchanged.
- **Rejected:** feedback that contradicts known cases ("kindle" → Entertainment, when the holdout says Kindle Unlimited is Education).

**Scheduling.** [`.github/workflows/retrain.yml`](../../.github/workflows/retrain.yml) runs weekly once `ENABLE_RETRAINING=true` and the Supabase secrets are set. It uploads the report and the challenger as a build artifact, and never deploys anything.

## 5. Experiment log

Every training or evaluation run appends a line to `reports/<kind>/runs.jsonl`: the commit, the parameters and the headline metrics. `python -m training.runs` prints the history, so a regression can be traced to the commit that caused it:

```
2026-10-18T13:43:05+00:00  2f04fd9  assistant    intent 1.000  slots 1.000  follow_ups 1.000
2026-10-18T13:43:10+00:00  2f04fd9  quickadd     amount 1.000  date 0.975  type 0.988  title_f1 0.982  all_fields 0.950
```

MLflow does this, and much more, for teams. For one service a JSON-lines file per kind does the job with no server to run. The logs are git-ignored; CI uploads its own with the reports.

## 6. Deployment (free)

**Memory, measured:**

| Part | Memory |
|---|---|
| App and categorizer | about 200 MB |
| Help-center embedding model (ONNX) | about **370 MB** more |

**Render** (the blueprint is in [`render.yaml`](../../render.yaml)):
1. Click [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ketulmehta13/ExpenseTracker) (or choose **New → Blueprint** in the Render dashboard and pick this repository). Enter `SUPABASE_URL` and `SUPABASE_ANON_KEY`: the same public values as the frontend's `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
2. The first build installs the dependencies, bakes the embedding model and trains the categorizer: about 5–10 minutes. When it's live, `https://<service>.onrender.com/health` returns `"status": "ok"`.
3. On the free plan (512 MB) the blueprint sets `EMBEDDING_MODEL=none`, so help search runs on keywords alone. On test questions that's 0.73 hit@1 instead of 0.83. With 1 GB or more, delete that entry.
4. Free services sleep after 15 minutes, and waking one takes about a minute (measured: 52 s). Keep it awake with a ping from Supabase every 5 minutes. Run this once in the SQL editor:

   ```sql
   create extension if not exists pg_cron;
   create extension if not exists pg_net with schema extensions;
   select cron.schedule('keep-ml-warm', '*/5 * * * *',
     $$select net.http_get('https://expense-ml-service-nsuf.onrender.com/health')$$);
   ```

   One always-on free service uses about 744 of Render's 750 free hours a month. The GitHub Actions workflow `keep-warm.yml` pings too, but GitHub delays scheduled runs to every few hours, so on its own it isn't enough. The app also wakes the service when it opens and waits up to 75 s for the assistant.
5. In Vercel, set `VITE_ML_API_URL` to the service's URL (e.g. `https://expense-ml-service.onrender.com`, no trailing slash) and redeploy. Vite reads it at build time, so a redeploy is required.
6. Apply the feedback migration to Supabase: paste `supabase/migrations/20261018000000_ml_feedback.sql` into the SQL editor and run it. It is re-runnable. Until then, everything works except the "Help improve category suggestions" setting, and no feedback is recorded.

The service only accepts requests from the origins in `ALLOWED_ORIGINS` (the production site). Add a preview URL there to try the features on a Vercel preview.

**Alternative: Hugging Face Spaces** (Docker SDK, 16 GB RAM on the free CPU tier). Full hybrid search fits. Create a Docker Space from `ml-service/`, set the same variables as Space secrets, and use port 7860 (`PORT=7860`).

## Interview questions this step answers

- *How do you monitor an ML service?*
  - System metrics: traffic, errors and latency per route.
  - Feature metrics: where suggestions come from, help declines, LLM fallbacks.
  - Product metrics: the acceptance rate of suggestions.

  Plus labels with bounded cardinality, and logs without user content.
- *How do you know a model degrades in production?* A falling acceptance rate and rising "no suggestion" counts: drift shows up there before anyone complains.
- *How do you retrain safely?* Champion/challenger on the same data. Promote only when the challenger is better on new data and no worse on known cases (a paired comparison), and keep a human in the loop for deploying.
- *How do you use user data responsibly?* Explicit opt-in (off by default), only titles, amounts and categories, row level security, an append-only log, and cascade deletion with the account.
- *Experiment tracking without MLflow?* An append-only run log with the commit, parameters and metrics. I'd move to MLflow once several people train models.
- *What did your own tests teach you about evaluation?* Small test sets need paired comparisons, and a weight on new data needs a cap. Both were caught by tests, not by users.
