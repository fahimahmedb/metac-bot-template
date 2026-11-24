# Paired economic comparator — frozen result

**Date: 2026-11-24. Research only. No promotion.**

## Execution evidence

- Tested commit: `a779bc8352a0829b2fa677b6d226c8d2e541b776`.
- [Run 45294407480](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45294407480): prediction job `138111027249` and score job `138111218486` succeeded.
- Same fixed 121 inputs as Qwen replay run `45294059131`: SHA-256 `80cc1d965c61e981f481c1902c385305903dfa5ab2f007f3cfa370c523d5597e`. 48 training, 32 validation, 41 test.
- Frozen numerical predictions SHA-256: `35353a117a21cbf6b94234696f677c0d15e32bfc05d747020f70cda88784d7e4`.
- Scoring artifact `14876630009`, ZIP SHA-256 `2acfecb65a7f1652b3cb837be2f85001ab84587d1fb880ac24c928b728c98c06`.
- All target dates and observed values were checked against pinned historical question snapshots (ForecastBench dataset commit `86b92ba06ed34d606d633bff3e99af54dd447d3a`). Source: ForecastBench, CC BY-SA 4.0.

## Actual results

| Policy | Validation Brier (32) | Test Brier (41, descriptive unless selected) |
|---|---:|---:|
| Neutral 50% | 0.250000 | 0.250000 |
| Historical empirical | 0.243846 | 0.265219 |
| Recent empirical | 0.273513 | 0.267951 |
| Momentum | 0.294791 | 0.227526 |
| Mean reversion (selected on validation) | 0.220963 | 0.285148 |

Validation selected mean reversion before test scoring. On held-out data it lost 0.035148 Brier points versus neutrality; log loss 0.765493 versus 0.693147. Momentum did better than 50% descriptively, but performed worst on validation: selecting it after seeing this test would invalidate the holdout. No method is promoted. Only 21 of 41 test rows had at least three comparable historical pairs; median was three. All 41 matched the strict-increase template.

## Interpretation and limitations

- ForecastBench's forecast-date value can differ from the earlier freeze value; these sparse snapshot trends are proxies, not a fully reconstructed real-time series.
- Revisions in pinned archives and dependence across related economic series are possible. No complete point-in-time vintage audit or domain transfer proof.
- This is a paired comparator on the same holdout as Qwen replay, not a new independent test.
- The joint hybrid comparison was specified in commit `56be30a660772f32279067df6ef49a674de39b1b` before reading these numeric test results; its evaluation remains contingent on completed LLM inference. No post-test change to its candidate weights or validation selection allowed.
- **NO_CHANGE_REQUIRED** for production. A larger independent series/time holdout is required to test regime-dependent momentum or reversal. Do not reuse these 41 outcomes to claim independent confirmation.

No official Metaculus forecast or LOT01 data used.