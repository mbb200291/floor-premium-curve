# Pilot result

## Scope

This pilot uses a public mirror of Taiwan presale real-price registration data covering ROC 111/11/01–111/11/10 (2022-11-01–2022-11-10).

- Source rows: 1200
- Residential rows after basic validity/special-transaction filtering: 947
- Rows with a strictly identifiable same-unit stack: 487
- Comparable stacks (>= 3 transactions and >= 3 distinct floors): 28
- Observations in the strict curve: 107
- Assumed floor-to-floor height: 3.2 m

The raw pilot file is data/pilot/AllPreData.csv. Its upstream Git blob SHA is 0dea2ba8409808e1e2f08bac673566713762d55e.

## Method

For each comparable project/stack, unit price is divided by that stack's median unit price. The reported premium is:

premium_pct = (unit_price / stack_median_unit_price - 1) * 100

The chart aggregates those within-stack premiums by floor. The plotted line is the median; the shaded band is the interquartile range. Floor 1 is kept in the CSV but excluded from the main line because ground-floor units often have qualitatively different attributes.

## Curve

| Floor | Est. AGL (m) | n | Median premium | Q25 | Q75 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 3.2 | 9 | -3.24% | -9.78% | -0.44% |
| 3 | 6.4 | 7 | -3.68% | -6.86% | -2.62% |
| 4 | 9.6 | 5 | -1.41% | -1.45% | -1.39% |
| 5 | 12.8 | 10 | 0.00% | -1.67% | 0.00% |
| 6 | 16.0 | 10 | 0.17% | -0.24% | 0.60% |
| 7 | 19.2 | 13 | -0.08% | -2.85% | 0.21% |
| 8 | 22.4 | 10 | 0.00% | 0.00% | 1.56% |
| 9 | 25.6 | 6 | 0.20% | -0.21% | 0.64% |
| 10 | 28.8 | 6 | 0.62% | 0.00% | 2.48% |
| 11 | 32.0 | 6 | 0.43% | 0.10% | 0.76% |
| 12 | 35.2 | 5 | 0.20% | 0.00% | 1.43% |
| 13 | 38.4 | 8 | 0.14% | 0.00% | 0.48% |

## Interpretation

The pilot shows a clear low-floor discount in the strict same-stack comparisons: floors 2–3 are roughly 3% below the stack median. From around floors 5–8 the median effect is near zero, while floors 9–13 are mildly positive.

This is not yet a Taiwan-wide causal estimate. The snapshot covers only ten transaction days, and some floor buckets have small n. The next step is to run the same pipeline on multiple MOI releases and estimate a fixed-effects / spline model with confidence intervals.
