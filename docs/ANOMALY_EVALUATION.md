# Unusual-payment detection: method and evaluation

Spendly flags payments that are **unusually large compared with your own earlier payments**.
This page describes what the detector actually does, how it was evaluated, and what the
results do and don't show.

> **Not fraud detection.** A flag means "this is much bigger than what you usually pay here".
> Every evaluation label below was injected into *synthetic* data by a script. None of these
> numbers say anything about catching fraud or about how often real users would agree with a flag.

## 1. Audit of the previous version (≤ 2.1)

| Question | Finding |
|---|---|
| Method | Tukey's rule: flag if amount > Q3 + 1.5 × IQR **and** ≥ 2 × median. Simple rules, no statistical model. |
| Reference | Same merchant if it had ≥ 5 payments in total, else same category if ≥ 8. |
| History used | **All** payments in the current filter, including the payment itself and later ones. A March payment was judged against September's. That is look-ahead leakage, and it changes when you change the date filter. |
| Eligible rows | Expense debits only (refunds, transfers, income, card bills excluded). Correct, kept. |
| Explanation | Ratio, median, threshold and sample size. Kept and extended. |
| Review workflow | `anomaly_reviews` table (dismissed / expected). Kept; nothing changes a transaction's classification. |
| Tests | 9 behaviour tests; no labelled evaluation. |

## 2. Methods compared

All methods check **expenses only** and use integer paise. Amounts ≤ 0 can't exist (database constraint) and would be ignored.

| Method | Rule | Reference distribution |
|---|---|---|
| `rule` (baseline) | amount ≥ a hand-set threshold for its category (`config.ANOMALY.rule_thresholds`) | none |
| `iqr_full` (legacy) | amount > Q3 + k·IQR and ≥ r·median | merchant (≥ 5) else category (≥ 8), **whole history incl. future** |
| `iqr_prior` | same rule | merchant (≥ 5) else category (≥ 8), **strictly earlier dates only** |
| `robust_z_prior` (**default**) | robust z ≥ 3.5 and amount ≥ 2·median | same as `iqr_prior` |

**Robust z-score**: `z = 0.6745 × (amount − median) / MAD`, where MAD is the median absolute
deviation of the earlier payments. If MAD = 0 (most payments identical), the scale is
`1.2533 × mean absolute deviation`. If that is also 0 (every earlier payment identical), any
different amount has z = ∞, and only the ratio rule decides. So ₹18,001 rent after
twelve ₹18,000 payments is **not** flagged (ratio 1.0).

**Ratio rule** (amount ≥ 2 × median): stops tight distributions, such as metro rides at ₹40–₹60,
from flagging tiny differences.

**Merchant-consistency guard** (prior methods): if the category is the yardstick but the merchant
already has ≥ 1 earlier payment and this one is below 2 × their median, it isn't flagged. Without it
the 2nd–5th rent payment would be compared with cheap "Other" payments and flagged every month.

**Insufficient history**: a payment whose merchant has < 5 and category < 8 earlier payments is
**not checked**. It is never guessed to be normal or unusual, and the UI lists how many weren't checked.

**Why no Isolation Forest / ML.** The only signal available is a payment's amount relative to
earlier payments in its merchant or category: one dimension per group. Isolation Forest would
learn the same "far from the bulk" idea with less transparency, needs a contamination
parameter we can't set without real labels, can't give the "compared with your 12 earlier
payments, median ₹450" explanation, and adds a heavy dependency. With synthetic labels it
would also be tuned to the generator. The added complexity isn't justified.

## 3. Features

Used for the decision: amount; earlier payments at the same merchant (count, median, quartiles,
MAD); earlier payments in the same category (same statistics). Reported in the explanation
(not used to decide): days since the previous payment to the same merchant, number of
earlier payments, ratio to median, robust z. Nothing uses later transactions (except the
legacy method, kept only for comparison).

## 4. Evaluation dataset (`src/anomaly_eval.py`, seed 42)

12 months (2025) of one synthetic account, ~990 rows:

- **Ordinary purchases**: 15 merchants across 10 categories. Log-normal amounts per merchant:
  tight ones (metro sd 0.08, fuel 0.15) and loose ones (Amazon sd 0.9). Poisson counts per month.
- **Repeated transactions**: rent, Netflix, Spotify and Airtel at fixed amounts every month; a
  same-day identical pair of coffees every month.
- **Large legitimate purchases** (label 0, `legit_large`): a phone, a TV, flights, a medical bill.
- **Refunds, transfers, salary, card-bill payments**: present, never eligible.
- **Injected anomalies** (label 1): `inflated` 4–12 × merchant median (26), `moderate` 2.5–3.5 ×
  (14), `new_merchant` one-off store at 5–10 × category median (8), `early` inflated in January
  (4), and `small_unusual` ₹5–₹30 at usually expensive merchants (6).

Label definitions: **1 = injected by the generator**, 0 = everything else. `legit_large` is
deliberately 0: any amount-based method will flag it, and counting it as a false positive
shows how many false alarms a user would see. `small_unusual` is deliberately 1: no method here
looks for unusually small payments, so these show that blind spot.

## 5. Methodology

- **Temporal split.** Tune = Jan–Jun, test = Jul–Dec. Prior methods only ever see earlier payments.
  The legacy method sees all 12 months, so its test numbers are optimistic.
- **Population.** Eligible expenses dated in the period. Payments without enough history count
  as *not flagged*.
- **Metrics.** TP, FP, TN, FN; precision = TP/(TP+FP); recall = TP/(TP+FN); F1 = 2PR/(P+R).
  Each is `None` when its denominator is 0, and F1 = 0 when P + R = 0.
- **Parameters.** The defaults were fixed **before** evaluation: z ≥ 3.5 (Iglewicz & Hoaglin) and
  the 1.5 × IQR / 2 × median values from the previous version. A small grid search on the tune half
  is reported separately, to show what tuning would do.
- **Stability.** Default parameters are also run on 5 other seeds (test half), reported as mean ± sd.
- **Reproducible.** `python -m scripts.evaluate_anomalies` regenerates everything. A test checks
  that the committed `docs/anomaly_evaluation.json` equals a fresh run.

## 6. Results

Test half (Jul–Dec), seed 42, default parameters (from `docs/anomaly_evaluation.json`):

<!-- results -->

| Method | Params | TP | FP | FN | TN | Precision | Recall | F1 | Not checked | F1 over 5 other seeds (mean ± sd) |
|---|---|---|---|---|---|---|---|---|---|---|
| Category threshold rule | per-category thresholds | 10 | 3 | 24 | 417 | 0.769 | 0.294 | 0.426 | 0 | 0.583 ± 0.108 |
| IQR on full history (legacy) | iqr_multiplier=1.5, min_ratio_to_median=2.0 | 26 | 9 | 8 | 411 | 0.743 | 0.765 | 0.754 | 0 | 0.739 ± 0.018 |
| IQR on earlier payments | iqr_multiplier=1.5, min_ratio_to_median=2.0 | 26 | 9 | 8 | 411 | 0.743 | 0.765 | 0.754 | 68 | 0.737 ± 0.004 |
| Robust z-score on earlier payments | z_threshold=3.5, min_ratio_to_median=2.0 | 26 | 7 | 8 | 413 | 0.788 | 0.765 | 0.776 | 68 | 0.773 ± 0.034 |

Grid-searched on the tuning half (Jan–Jun), then applied to the test half (Jul–Dec):

| Method | Best params on tune half | Tune F1 | Test P | Test R | Test F1 |
|---|---|---|---|---|---|
| IQR on earlier payments | iqr_multiplier=1.5, min_ratio_to_median=3.0 | 0.810 | 0.783 | 0.529 | 0.632 |
| Robust z-score on earlier payments | z_threshold=3.0, min_ratio_to_median=3.0 | 0.864 | 0.760 | 0.559 | 0.644 |

Flags by kind of payment on the test half (flagged / count):

| Method | inflated | legit_large | moderate | new_merchant | ordinary | repeated_fixed | repeated_same_day | small_unusual |
|---|---|---|---|---|---|---|---|---|
| Category threshold rule | 5/14 | 3/3 | 2/10 | 3/5 | 0/381 | 0/24 | 0/12 | 0/5 |
| IQR on full history (legacy) | 14/14 | 3/3 | 9/10 | 3/5 | 6/381 | 0/24 | 0/12 | 0/5 |
| IQR on earlier payments | 14/14 | 2/3 | 9/10 | 3/5 | 7/381 | 0/24 | 0/12 | 0/5 |
| Robust z-score on earlier payments | 14/14 | 2/3 | 8/10 | 4/5 | 5/381 | 0/24 | 0/12 | 0/5 |

<!-- /results -->

## 7. What the results show

- **The legacy method's score was flattered by future data.** On the test half the leakage-free IQR
  gets the same TP/FP/FN as the legacy version, but the legacy version also "checked" 68 payments
  that had no earlier history, using later payments. On the tune half the legacy method
  checked all but 3 payments, while the leakage-free methods could check all but 66. Those extra checks
  are only possible because the legacy method looks at the future.
- **Robust z vs IQR.** With the same ratio rule, robust z had 2 fewer false positives on seed 42.
  It caught one more new-merchant anomaly and one fewer moderate one, so TP was the same. Over 5 other seeds the mean F1
  was 0.773 ± 0.034 vs 0.737 ± 0.004. The difference is about one standard deviation: a small,
  not decisive, improvement. Robust z is the default because it is slightly better here, handles
  constant amounts explicitly, and gives a single interpretable deviation number.
- **Tuning on six months overfit.** The grid search picked a stricter ratio (3 × median) that scored
  best on the tune half (24 anomalies), but recall on the test half dropped from 0.77 to ~0.55,
  because "moderate" anomalies are 2.5–3.5 × the median. The pre-set defaults were kept.
- **The hand-set category rule** is precise but misses most anomalies (recall 0.29): one threshold
  per category can't fit both a ₹50 metro ride and a ₹1,800 grocery order.
- **Blind spots, by design.** No method flags unusually *small* payments (0/5). Genuine large
  purchases are flagged (2/3), which is why every flag can be marked "expected" or dismissed.
- **No false flags** on fixed repeated payments, same-day identical pairs, refunds or transfers.

## 8. Limitations

- Labels are synthetic. Real spending is messier: seasonal, with life events and merchant renames.
  The generator also shares assumptions with the detector (log-normal amounts per merchant), which
  favours amount-based methods.
- 34 anomalies in the test half is a small sample. Differences of a few TP/FP are within noise.
- New users have little history: about 15% of payments in the test half couldn't be checked, and
  more early on.
- Merchant normalisation matters: if one shop appears under two names, its history is split.
- Only the amount is used. Timing (a 3 a.m. payment), location and frequency bursts aren't modelled.
  The data model has no time of day or location, and frequency would need its own evaluation.
- Severity bands (`notable` z < 6, `large` 6–10, `extreme` ≥ 10; ratio-based when z is infinite) describe
  the size of the deviation only. They are not risk scores.
