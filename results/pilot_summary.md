# Pilot result — special floors separated

## Sample

- Source rows: 1200
- Basic eligible residential rows: 947
- Strictly identifiable stack rows: 487
- Comparable stacks: 28
- Comparable observations: 107
- Regular-floor observations used for the main curve: 97
- First-floor observations: 2
- Top-floor observations: 8

## Main curve

The main height curve now excludes both first-floor and top-floor units. This avoids forcing special attributes of those units into the continuous height effect.

| Floor | Est. AGL (m) | n | Median premium | Q25 | Q75 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 3.2 | 9 | -3.24% | -9.78% | -0.44% |
| 3 | 6.4 | 7 | -3.68% | -6.86% | -2.62% |
| 4 | 9.6 | 5 | -1.41% | -1.45% | -1.39% |
| 5 | 12.8 | 10 | 0.00% | -1.67% | 0.00% |
| 6 | 16.0 | 10 | 0.17% | -0.24% | 0.60% |
| 7 | 19.2 | 11 | -0.33% | -3.02% | 0.11% |
| 8 | 22.4 | 10 | 0.00% | 0.00% | 1.56% |
| 9 | 25.6 | 6 | 0.20% | -0.21% | 0.64% |
| 10 | 28.8 | 6 | 0.62% | 0.00% | 2.48% |
| 11 | 32.0 | 4 | 0.19% | 0.00% | 0.41% |
| 12 | 35.2 | 5 | 0.20% | 0.00% | 1.43% |
| 13 | 38.4 | 5 | 0.28% | 0.00% | 0.39% |

## Special floors

| Category | n | Median AGL | Median premium | Mean premium | Height-adjusted? |
| --- | ---: | ---: | ---: | ---: | --- |
| First floor | 2 | 0.0 m | 4.02% | 4.02% | No |
| Top floor | 8 | 35.2 m | 0.81% | 1.63% | No |

The first-floor value is based on only two observations and is therefore not interpretable as a stable preference estimate. The top-floor summary is also not a pure top-floor effect because top-floor units occur at greater heights. A later regression/spline model must estimate height and special-floor indicators jointly.

## Interpretation

After removing special floors from the main line, the low-floor discount remains: floors 2–3 are around 3–4% below the same-stack median in this small snapshot. From around floors 5–8 the regular-floor median is close to zero, and floors 9–13 are mildly positive.

This remains a pilot based on a ten-day 2022 presale snapshot, not a Taiwan-wide final estimate.
