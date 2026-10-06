# Pilot result — descriptive + adjusted model

## Sample

- Source rows: 1200
- Strict stack rows: 487
- Comparable stacks: 28
- Comparable model observations: 107
- First-floor observations: 2
- Top-floor observations: 8

## Descriptive curve

The descriptive main line excludes first-floor and top-floor observations. The low-floor discount seen previously remains in the pilot.

## Adjusted within-stack model

Model:

    log(price) = stack FE + linear spline(height) + first_floor + top_floor + error

- knots: 12.8 m, 25.6 m, 38.4 m
- reference height: 12.8 m (about 5F)
- cluster-robust SE by stack
- observations: 107
- clusters: 28
- within R²: 0.5079

### Special floors

| Effect | n | Adjusted estimate | 95% CI | Status |
| --- | ---: | ---: | ---: | --- |
| First floor | 2 | 9.86% | 4.62% ~ 15.35% | insufficient_sample |
| Top floor | 8 | 0.35% | -2.91% ~ 3.71% | insufficient_sample |

Neither estimate is reportable under the current n >= 10 rule. First-floor estimation is especially fragile because n=2 and the ordinary height function at 0 m is extrapolated from floors above ground.

### Adjusted height curve

The model curve is stored in data/processed/pilot_model_curve.csv and expressed relative to 12.8 m / about 5F. This curve is experimental because the pilot has only 107 observations and ten transaction days.

The purpose of this stage is to validate the estimator and output contract; it is not yet a Taiwan-wide preference estimate.
