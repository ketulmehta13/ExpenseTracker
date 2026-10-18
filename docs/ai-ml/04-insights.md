# Step 4 — Spending insights

**What it does:** the dashboard shows three cards, computed from the user's last ~13 months:

- **Month-end forecast:** "₹30,418, likely ₹25,911–₹34,926 · Budget ₹40,000 · very unlikely to go over".
- **Subscriptions & bills:** each detected recurring payment, its rhythm, its next due date, and the monthly total.
- **Unusual spending:** recent payments far above the user's normal range ("11× your usual top payment here"). Those rows also get a badge on the Transactions page.

**Where it lives:**

| Piece | File |
|---|---|
| Unusual spending | [`ml-service/app/ml/anomaly.py`](../../ml-service/app/ml/anomaly.py) |
| Recurring payments | [`ml-service/app/ml/recurring.py`](../../ml-service/app/ml/recurring.py) |
| Month-end forecast | [`ml-service/app/ml/forecast.py`](../../ml-service/app/ml/forecast.py) |
| API endpoint | [`ml-service/app/routers/insights.py`](../../ml-service/app/routers/insights.py) |
| Simulated users with ground truth | [`training/simulate_history.py`](../../ml-service/training/simulate_history.py) |
| Evaluation and gate | [`training/evaluate_insights.py`](../../ml-service/training/evaluate_insights.py) |
| Latest results | [`reports/insights/report.md`](../../ml-service/reports/insights/report.md) |
| Frontend | [`SpendingInsights.jsx`](../../frontend/src/components/SpendingInsights.jsx), [`Transactions.jsx`](../../frontend/src/pages/Transactions.jsx) |

## Results at a glance

All numbers are on 100 simulated **test** users, after every threshold was chosen on 100 different **validation** users.

| Detector | Result | Best alternative |
|---|---|---|
| Unusual spending | F1 **0.995** | 0.873 (robust z-score on amounts, tuned) |
| Recurring payments | F1 **0.998**, period right 100% of the time | none |
| Month-end forecast | MAPE **14.0%** (6.9% by day 25) | 33.1% (last month's total) |
| 80% forecast interval | contains the actual total **81.0%** of the time | 66% before calibration |

## 1. How do you evaluate without labels? Simulate users with known answers

Real transactions are private and unlabelled. Nobody has marked which payments were "unusual". So [`simulate_history.py`](../../ml-service/training/simulate_history.py) generates a year of transactions per user, where the answers are known by construction:

- **Recurring payments** (rent, Netflix, a 28-day Jio plan, a weekly cleaner) with realistic mess:
  - title variants ("Netflix", "NETFLIX.COM", "UPI/HOUSE RENT/88213/Pay");
  - a day or two of jitter;
  - occasional price rises;
  - series that start late or get cancelled.
- **Everyday spending** (Swiggy, Uber, Amazon) at random times, with heavy-tailed (lognormal) amounts, so a legitimately big purchase happens now and then. These are the **hard negatives**: frequent but not recurring, large but not anomalous.
- **Injected spikes**: 5–15× the top of the user's normal range at that merchant.

**Validation users vs test users.** Every threshold and constant is chosen on one group of simulated users and reported on another. It is the same discipline as a train/test split: a score measured on the data that chose the threshold is optimistic.

## 2. Unusual spending: what failed first, and why

### Attempt 1: robust z-score (the textbook answer), F1 0.53
```
robust z = 0.6745 · (x − median) / MAD,   MAD = median(|x − median|)
```
- The median and MAD (median absolute deviation) are **robust**: a few outliers barely move them.
- The classic z-score uses the mean and standard deviation, which the outliers themselves inflate. So big payments hide each other, which is called **masking**.
- The score is computed on log amounts per category, and 3.5 is the conventional cut-off (Iglewicz and Hoaglin).

It scored F1 0.53. Reading the errors, rather than tuning blindly, showed three separate problems. Each fix is a row in the ablation table below.

1. **Categories mix price levels.** "Other" holds a ₹400 weekly cleaner and a ₹3,500 monthly maid, so every maid payment looked unusual. *Fix: compare with the same merchant first, and fall back to the category only when the merchant has fewer than 8 payments.*
2. **Fixed-price payments collapse the MAD to zero.** A rent group has no spread, so any change looks infinitely unusual. *Fix: leave recurring payments out. They have their own detector.*
3. **The z-score's bar scales with the spread.**
   - At Amazon (a ₹300 cable or a ₹4,000 jacket), the spread is so wide that spikes 17–60× the usual amount scored only z ≈ 2.4–3.0 during development.
   - Merchants with a few similar payments had a tiny MAD and raised false alarms.

   *Fix: change the question, below.*

### What shipped: a percentile ratio
```
ratio = amount / P90(the user's other payments at that merchant)     unusual if ratio ≥ 6
```
- **"How far above your normal range?" rather than "how many spreads from the middle?"**, so wide-ranging merchants no longer hide spikes.
- **Leave-one-out.** A payment is never part of its own baseline. Computing the 90th percentile of "everyone but me" for every payment is done in O(n log n) from one sorted array, not O(n²).
- **Robust to masking.** One earlier spike sits above the 90th percentile, so it doesn't raise the bar for the next.
- **It explains itself:** "₹3,141 at Ola, 11× your usual top payment here (₹285)".
- **Guards.** At least 8 payments in the group, and never below ₹500.

### Ablation and baselines (test F1)

| Method | F1 |
|---|---|
| z-score on amounts, per category (tuned threshold 5) | 0.854 |
| robust z on amounts, per category (tuned threshold 20) | 0.873 |
| Isolation Forest on log amounts, per category (tuned) | 0.840 |
| robust z on log amounts, per category | 0.531 |
| + merchant's own history first | 0.827 |
| + recurring payments left out | 0.914 |
| **percentile ratio instead of z-score (shipped)** | **0.995** |

**Isolation Forest** isolates points with random splits; outliers need fewer splits. It works on any distribution shape, but:
- its score has no unit a user understands;
- it needs fitting per user and category;
- its validation curve was sharp (F1 0.85 at cut-off 0.75, but 0.72 at 0.70 and 0.68 at 0.80).

The ratio's curve is flat: F1 stays within 2 points of its best anywhere from 4× to 7×. A threshold that doesn't need to be exact is a robust one.

### The caveat to say out loud
The simulator defines a spike relative to the top of the normal range. That is close to what the percentile ratio measures, so 0.995 is an **upper bound**, partly circular. The informative result is the comparison between methods on identical data. In production the real metric is **how often users dismiss an alert**, and the next step is to log it.

## 3. Recurring payments: periodicity detection

1. **Group by merchant.** A merchant key normalizes titles: lowercase, payment-rail noise removed, month names and filler dropped. "Rent for October", "rent nov" and "UPI/HOUSE RENT/1234/Pay" each collapse to a stable key.
2. **Check the rhythm.** The median gap between payments must match a known period: weekly, fortnightly, every 28 days (prepaid mobile plans), monthly, quarterly or yearly.
3. **Check it's regular.** At least 75% of the gaps must fall within that period's tolerance, so one skipped month doesn't break a series. A share-based test is more robust than the coefficient of variation of the gaps, which a single long gap would blow up.
4. **Check the amount is stable.** The coefficient of variation (std / mean) must be at most 0.35. That allows a varying electricity bill, but not a basket of random purchases.
5. **Predict the next payment** in calendar months for monthly bills ("the 7th of next month"), not "last date + 31 days". A test caught exactly that bug.

Hard negatives (Swiggy three times a week) fail the regularity test: their gaps look exponential, not periodic.

## 4. Month-end forecast

```
projected = spent so far this month
          + Σ over remaining days of the average everyday spend for that weekday (last 90 days)
          + recurring payments still due this month
```
- **Decomposition beats extrapolation.**
  - The naive **run-rate** (spent ÷ days so far × days in month) is 61% wrong on day 5, because rent paid on the 3rd gets extrapolated as if rent were paid every day.
  - Separating recurring payments, which are added on their due dates, from everyday spending, which is spread by weekday, brings the error to 20.5% on day 5 and 6.9% by day 25.
- Detected anomalies are excluded from the everyday rate: a one-off is not a run-rate.
- **Backtesting**, the time-series version of a test set: forecast on days 5, 10, 15, 20 and 25 of six past months, using only the data available on that day. There are no future leaks.

| Method | Overall | Day 5 | Day 15 | Day 25 |
|---|---|---|---|---|
| last month's total | 33.1% | 33.1% | 33.1% | 33.1% |
| run-rate | 34.6% | 60.9% | 32.6% | 11.9% |
| **shipped** | **14.0%** | **20.5%** | **14.4%** | **6.9%** |

### An honest uncertainty band: calibration by split conformal prediction
Treating the remaining days as independent, their variances add up, which gives a textbook 80% interval of ±1.28σ. In the backtest it contained the actual total only **66%** of the time, because:
- real days are correlated;
- the weekday averages are themselves estimates.

The fix is **split conformal prediction**:
1. On the validation users, measure the forecast errors in units of the textbook σ.
2. Take their 80th percentile. That says how much to widen σ: 1.42×, shipped as 1.45×.
3. On the test users, the interval now contains the actual total **81.0%** of the time.

The same calibrated σ gives the **probability of going over budget**: 1 − Φ((budget − projected) / σ).

## 5. Serving

- **Endpoint.** `GET /v1/insights?today=YYYY-MM-DD` reads ~13 months of the user's transactions, their categories and their budget, **with the user's own token** (row level security still applies). It computes all three insights in milliseconds and caches the result per user and day for 60 seconds.
- **Nothing is stored.** There are no new tables, migrations or admin keys.
- **The client sends its local date.** The server's UTC date can be a day behind India's. Dates more than a day from the server's are rejected.
- **The frontend degrades gracefully.**
  - It allows an 8-second timeout, since the first call reads a year of data.
  - It keeps the last good result if a refresh fails.
  - It renders nothing at all when `VITE_ML_API_URL` is unset.

## 6. MLOps in this step

- **CI evaluation gate.** `python -m training.evaluate_insights --gate` fails the build if, on test users:
  - unusual-spending F1 drops below 0.95;
  - recurring-payment F1 drops below 0.95;
  - the forecast stops beating the better baseline by 10 points;
  - the 80% interval stops covering 75–85% of outcomes. Too wide is a regression too.
- **Report.** [`reports/insights/report.md`](../../ml-service/reports/insights/report.md) is regenerated on every run and uploaded as a CI artifact.

## Reproduce

```bash
cd ml-service
python -m training.evaluate_insights --gate     # about 2 minutes
```

## Interview questions this step answers

- *How do you evaluate an unsupervised feature with no labels?* Simulate data with known ground truth. Include realistic hard negatives. Tune on one set of simulated users and report on another. And be clear about where simulation stops being evidence.
- *Why is a robust z-score better than a z-score, and when does it still fail?* Median and MAD resist masking. But a spread-based bar fails on multi-modal groups, on zero-spread groups and on very wide distributions.
- *How did you pick the anomaly threshold?* Maximum F1 on validation users, checking that the curve is flat around the choice, then reported on test users.
- *Isolation Forest vs. a rule?* The forest is distribution-free but opaque, needs per-user fitting and had a sharp optimum. The rule is interpretable, fast and stable. Both were measured on the same data.
- *How do you detect subscriptions?* Merchant normalization, then the median gap matched to known periods, a share of regular gaps, and amount stability, with calendar-aware next dates.
- *How do you evaluate a forecast?* A backtest with no future data, MAPE by forecast horizon, and comparison with naive baselines (last month, run-rate).
- *Your interval said 80% but covered 66%. What did you do?* Split conformal calibration on held-out users, and verified 81% coverage on test users.
- *What's next?* Log alert dismissals and suggestion acceptance (step 9), weight recent behaviour more, and detect price changes in subscriptions.
