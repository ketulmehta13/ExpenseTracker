# Step 3 — Transaction categorizer

**What it does:** while the user types a transaction title, the form suggests a category ("✨ Suggested: Food · 94% sure — tap to apply"). One tap applies it.

**Where it lives:**

| Piece | File |
|---|---|
| Title normalization | [`ml-service/app/ml/text.py`](../../ml-service/app/ml/text.py) |
| Features and model | [`ml-service/app/ml/categorizer.py`](../../ml-service/app/ml/categorizer.py) |
| User-history matching | [`ml-service/app/ml/history.py`](../../ml-service/app/ml/history.py) |
| Label → user category mapping | [`ml-service/app/ml/taxonomy.py`](../../ml-service/app/ml/taxonomy.py) |
| API endpoint | [`ml-service/app/routers/categorize.py`](../../ml-service/app/routers/categorize.py) |
| Training data | [`training/generate_data.py`](../../ml-service/training/generate_data.py), [`training/data/holdout_real.csv`](../../ml-service/training/data/holdout_real.csv) |
| Training and evaluation | [`training/train_categorizer.py`](../../ml-service/training/train_categorizer.py) |
| Latest results | [`reports/categorizer/model_card.md`](../../ml-service/reports/categorizer/model_card.md) |
| Frontend | [`services/mlService.js`](../../frontend/src/services/mlService.js), [`TransactionModal.jsx`](../../frontend/src/components/TransactionModal.jsx) |

## Results at a glance

| Measure | Value |
|---|---|
| Macro-F1 on 142 hand-written titles | **0.888** (majority-class baseline: 0.016) |
| Suggestions shown at threshold 0.70 | 56% of entries |
| Precision of the suggestions shown | **97.5%** |
| Prediction latency | about 4 ms on a laptop CPU |
| Model size | 0.6 MB, CPU only |

## 1. Framing the problem

This is **multi-class text classification**. The input is a title, an amount and a type (income or expense). The output is one of ten canonical labels: food, travel, shopping, utilities, entertainment, health, education, rent, salary, other.

Users name their categories however they like ("Food", "Groceries", "Dining Out"). The model therefore predicts a **fixed canonical taxonomy**, and the server maps the label onto the user's own category through a list of aliases, preferring a category the user created over a shared default. When the user has no matching category, the suggestion says so ("+ Health — tap to create & use").

## 2. Data without user data

There is no labelled dataset, and real transactions are private. Training uses **synthetic data**: 178 phrase templates for Indian merchants and payment types. Each template is rendered in the formats real statements use (plain, Title Case, `UPI/SWIGGY/40213/Payment`, `AMZN*ORDER 4432`, `POS 1234 DMART`), with 15% typos. The result is 6,000 rows.

### Leakage: the most important decision in this step
Renderings of the same template are near-duplicates. With a **random** train/test split, the test set contains rows the model has effectively already seen, and macro-F1 comes out at **0.993**. That number measures memorisation.

The test split is therefore **grouped by template** (`StratifiedGroupKFold`): every test title comes from a phrase the model never saw. Macro-F1 drops to **0.532**, because on that test set the merchant name itself is always new.

### A hand-written holdout set
Neither synthetic number tells you how the model does on real input. [`holdout_real.csv`](../../ml-service/training/data/holdout_real.csv) holds **142 hand-written titles**. They include messy formats, merchants the generator never uses (Blinkit, Akasa Air, Lal PathLabs) and deliberately tricky entries ("amazon prime membership" is entertainment, not shopping). It is never used for training, tuning or picking the threshold.

The three numbers bracket reality:

| Evaluation | Macro-F1 | What it measures |
|---|---|---|
| Random split (leaky) | 0.993 | Memorisation: an inflated number, shown only for contrast |
| Grouped split | 0.532 | Generalisation to merchants never seen: a pessimistic bound |
| Hand-written holdout | **0.888** | A realistic mix of known and unknown merchants |

## 3. Features

**Shared normalization, so training and serving match.** `normalize_title` lowercases, strips payment-rail words (UPI, NEFT, POS, "paid to"), drops reference numbers and masked card digits, keeps short brand names with digits (1mg, zee5) and expands abbreviations (AMZN → amazon). Training and serving call the same function, which prevents **train/serve skew**, a classic production bug.

| Raw title | Normalized |
|---|---|
| `UPI/SWIGGY/40213/Payment` | `swiggy` |
| `AMZN MKTP IN` | `amazon` |
| `paid to Zomato order ref 99812345` | `zomato` |
| `BMS*BOOKMYSHOW 2201` | `bookmyshow` |

Four feature groups are combined by a `ColumnTransformer` into one sparse matrix:

1. **Word TF-IDF (1–2 grams).** TF-IDF weights a word by how often it appears in this title (term frequency, here sublinear: 1 + log tf), times how rare it is across all titles (inverse document frequency). "rent" counts for a lot; "monthly" counts for little. Bigrams capture phrases such as "house rent" and "credit card".
2. **Character TF-IDF (2–5 grams within word boundaries).** This makes the model robust to typos ("swigy" shares most of its character n-grams with "swiggy") and lets it generalise from merchant fragments ("pharm" appears in both Apollo Pharmacy and PharmEasy).
3. **Amount band.** `log1p(amount)` is cut into 8 quantile bins and one-hot encoded. Bins rather than the raw number, because the relationship isn't monotonic: rent is large, groceries small, shopping in between. A linear model can only learn a monotonic effect from a raw number.
4. **Transaction type** (income or expense), one-hot encoded. It separates salary from everything else.

## 4. Model: logistic regression

Multinomial logistic regression is a linear model with a softmax over the ten classes.

**Why it, rather than a transformer?**
- It is a strong baseline for short, sparse text.
- It trains in seconds and predicts in about 4 ms on a CPU, from a 0.6 MB model file.
- Its outputs are probabilities, which the threshold needs.
- It is interpretable: every n-gram has a weight per class.

A sentence-embedding model (such as MiniLM) is a valid experiment. Under this project's rules it ships only if it beats this model on the same holdout.

- **`class_weight="balanced"`:** errors on rare classes cost more, so frequent categories can't drown them out. That matters once real feedback data, which is imbalanced, is added.
- **Regularisation strength C** was chosen by **grouped** 5-fold cross-validation over 0.1–8. Plain cross-validation would leak templates across folds, just as a random split does. The scores are flat between 0.25 and 8 (0.553–0.560), so the model isn't sensitive to C. C = 1.0 won.

### Ablation: does each part earn its place?
All rows below are trained on the training split only, with C = 1.0.

| Model | Grouped test | Holdout |
|---|---|---|
| Majority class | 0.015 | 0.016 |
| Words only | 0.472 | 0.737 |
| + character n-grams | 0.502 | 0.774 |
| + amount band and type (full) | 0.532 | 0.817 |
| Full, refit on all synthetic data (shipped) | n/a | **0.888** |

The last row shows that the biggest single gain is **more templates**: refitting on the 20% of templates held back for testing adds 7 points on the holdout. More (and more varied) data beats any model tweak here.

## 5. Metrics and errors

**Why macro-F1 rather than accuracy:**
- F1 is the harmonic mean of precision and recall.
- Macro-F1 averages F1 over classes with equal weight, so a model that ignores a small class like education is punished, even if overall accuracy looks fine.
- Accuracy is reported alongside it.

**Reading the confusion matrix** in the [model card](../../ml-service/reports/categorizer/model_card.md) shows systematic errors, not random ones:
- **The amount band misleads on large one-off purchases.** "semester fees ₹45,000" and "Vijay Sales TV ₹32,990" are predicted as rent because they sit in rent's amount range.
- **Shared brands.** "hp gas" is utilities, but "hp petrol" in the training data is travel.
- **Ambiguous merchants.** "amazon prime membership" could be shopping or entertainment.

These are exactly the cases the user's own history fixes, which is why history is checked first.

## 6. Deciding when to show a suggestion

A wrong suggestion costs the user's trust; a missing one costs a click. The model therefore suggests something only when its top probability passes a **threshold**. That is a **precision–coverage trade-off**:

| Threshold | Out-of-fold precision | Out-of-fold coverage | Holdout precision | Holdout coverage |
|---|---|---|---|---|
| 0.5 | 81.7% | 37.1% | 94.2% | 73.2% |
| 0.6 | 84.9% | 32.2% | 95.7% | 66.2% |
| **0.7** | **92.1%** | **26.8%** | **97.5%** | **55.6%** |
| 0.8 | 97.6% | 22.2% | 100% | 47.9% |

**How the threshold is chosen without touching the holdout:**
- `cross_val_predict` gives **out-of-fold** probabilities: every training row is scored by a model that never saw its template.
- The threshold is the **lowest** value at which those suggestions are at least 90% correct. Lowest means coverage stays as high as possible.
- Out-of-fold data is the hard, all-new-merchant case, so the precision guarantee is conservative. On realistic input it comes out at 97.5%.

### Calibration
A model is **calibrated** if its 70%-confidence predictions are right 70% of the time. **Expected calibration error (ECE)** measures the gap: it bins predictions by confidence and averages |accuracy − confidence|, weighted by bin size.
- On the grouped test set, ECE is 0.08.
- On the holdout, ECE is 0.19. The model averages 0.70 confidence but is right 0.89 of the time: it is **underconfident** on realistic input.

That is the safe direction for a suggestion feature. If it ever needs fixing, temperature scaling or `CalibratedClassifierCV` fitted on real feedback is the tool.

## 7. Serving: a cascade

```
POST /v1/categorize {title, amount, type}
   │
   ├─ 1. The user's own history (cached for 60 s per user, read with the user's token under RLS)
   │      exact or fuzzy title match (rapidfuzz token_sort_ratio ≥ 88)
   │      confidence = similarity × share of that title filed under the category ≥ 0.6
   │      → "Dining Out · from your history"
   │
   ├─ 2. The model, if its top probability ≥ 0.70
   │      label → the user's category through aliases (or "+ Health" if none)
   │      → "Food · 94% sure"
   │
   └─ 3. No suggestion
```

- **History comes first** because people repeat themselves, and personal habits beat any global model. One user files Amazon under Shopping, another under Household. The model covers the cold start.
- **Choice of fuzzy scorer.** `token_sort_ratio` ignores word order and absorbs a typo. `partial_ratio` and `token_set_ratio` were rejected because they score "uber" against "uber eats", and "rent" against "car rental", as near-perfect matches.
- **Graceful degradation.**
  - The frontend gives up after 2 seconds and cancels a request as soon as the user types again, so a stale answer never overwrites a newer one. A failure just means no chip.
  - If the service has no model file, it still starts and falls back to history matching.
  - With `VITE_ML_API_URL` unset, the feature is hidden.
- **Privacy.** The service reads only titles and category ids, with the user's own token. Logs record the source and the confidence, never the title.

## 8. MLOps in this step

- **Reproducible.** Fixed seeds. The model version is the date plus a hash of the training data and parameters.
- **Model card.** Every training run writes [`model_card.md`](../../ml-service/reports/categorizer/model_card.md) and `metrics.json`, following *Model Cards for Model Reporting* (Mitchell et al., 2019): intended use, data, metrics, the worst mistakes and limitations.
- **Evaluation gate.**
  - CI trains the model and **fails the build if holdout macro-F1 drops below 0.80**.
  - The Docker build runs the same gate, so a weak model can never ship in an image.
  - CI uploads the reports as a build artifact.
- **Training inside the image.** The model is a pickle. Training inside the image guarantees it matches the installed scikit-learn version. Pickles can execute code when loaded, so the service only loads files it produced.
- **Next ([step 9](README.md#roadmap)).**
  - Log whether each suggestion is accepted or overridden.
  - Retrain on that feedback, and promote a new model only when it beats the current one on the gate.

## Reproduce

```bash
cd ml-service
python -m training.train_categorizer --min-holdout-f1 0.80
```

## Interview questions this step answers

- *How did you get training data without real user data?* Template-based synthetic generation with realistic noise, plus a hand-written holdout set for an honest estimate.
- *How did you avoid data leakage?* Group-aware splitting by template, for the test split and inside cross-validation. A random split reports 0.99; the honest number is far lower.
- *Why macro-F1?* Every category matters equally, and accuracy hides a model that ignores small classes.
- *Why logistic regression rather than BERT?* Small sparse inputs, CPU-only, 4 ms latency, calibrated-enough probabilities, interpretability. A bigger model has to win on the same holdout to ship.
- *How did you choose the confidence threshold?* Out-of-fold predictions, with the lowest threshold that meets a precision target. Precision matters more than coverage for suggestions.
- *What is ECE, and is your model calibrated?* ECE is the bin-weighted gap between confidence and accuracy. This model is underconfident on realistic input, which is the safe direction here.
- *How do you prevent train/serve skew?* One normalization function and one `to_frame` used by both training and serving, plus training inside the serving image.
- *How do you personalise a global model?* A cascade: the user's own history first (fuzzy matching), then the global model, then a mapping onto each user's own category names.
- *What would you improve next?*
  - A feedback loop and retraining.
  - Weighting history by recency.
  - Active learning on low-confidence entries.
  - An embedding-based model as a challenger.
