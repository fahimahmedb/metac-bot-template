# Second holdout — text prior and provider-balanced ensembles

**Frozen result: 2026-11-24.** No production change. Research-only PR #3.

- Tested code: `ec6a488459759e190fe050a6c6067bf419f4a332`.
- [Run 45293654050](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45293654050), job `138108459328`: eight unit tests passed; pinned dependencies installed; archive hash verified; actual fit, selection and evaluation completed; report uploaded.
- Artifact `14875511050`, ZIP SHA-256 `143a4aea0c8519f84c689b12653c9fbdd2f685c77612ee2b76ddc34fdc3db566`.
- Same immutable-by-hash archive as experiment 1: `3b3b9630f2ccf4da401e703266a116cdc7de535eabb4cb44c9a10d1c01315b0f`. Question snapshots pinned to ForecastBench dataset commit `86b92ba06ed34d606d633bff3e99af54dd447d3a`. Source: ForecastBench, CC BY-SA 4.0.
- 6,711,199 archive rows scanned, 190,207 eligible forecast rows, 1,422 partitioned event IDs, 1,419 retained distinct question texts. No LOT01 data used.

## Frozen protocol

Train forecasts before 2026-04-01, validation 2026-04-01 through 2026-06-30, test 2026-07-01 through 2026-10-25. Label freeze 2026-11-20, 30-day training/validation embargo. Old event IDs excluded from new test; exact question deduplication among partitioned events; semantic duplicates remain possible. Train TF-IDF and logistic regression on training text only, select regularization on validation, then predict masked test inputs. Question title only, URL/year masking; no explicit market context or outcomes in prediction input. Two separately reported ensemble strata with and without explicit market context, no mixing.

## Actual metrics

| Candidate | Train | Validation | Test | Test Brier | Test log loss |
|---|---:|---:|---:|---:|---:|
| Historical train base rate (15.279%) | 947 | 112 | 360 | 0.291467 | 0.827166 |
| TF-IDF logistic, C=0.1 | 947 | 112 | 360 | 0.286825 | 0.810469 |
| Constant 50% | — | — | 360 | 0.250000 | 0.693147 |

Validation Brier: historical rate 0.296151, C=0.1 0.288716, C=1 0.299891, C=10 0.330055. C=0.1 selected before test scoring.

Brier gain versus historical rate = 0.0046419 (1.59% relative); round-block bootstrap interval [0.001533, 0.009105], nine rounds, descriptive only. Selected model classification accuracy 61.39%, exactly the same as historical rate. Test positive prevalence 38.61%; a major distribution/selection shift relative to training. The learned prior is **worse than 50% by 0.036825** and has not earned promotion. Note the 50% threshold accuracy is tie-breaking dependent, not a meaningful skill metric for that constant.

Ensembles: both strata had 947 training and 112 validation observations with two or more providers, but zero test observations satisfying the exact pairing requirements. **BLOCK_INSUFFICIENT_COVERAGE**, not a negative performance result. ForecastBench official variant declarations show several independent variants no longer active, but this is not proof of the exact cause of missing paired test rows.

## Challenge and decision

- Label-availability embargo and requiring completed resolutions can select fast-resolving outcomes differently across periods; labels' resolution dates are only a proxy for publication time. The prevalence shift makes a pooled historical rate unreliable.
- Pinned snapshots were retrieved from the current dataset commit; this does not prove historical text was never revised. No semantic event deduplication, no causal attribution of the gain.
- **PASS** for execution and temporal/masking invariants tested.
- **REJECT / NO_CHANGE_REQUIRED** for adopting this text-only predictor.
- **BLOCK** for conclusions about ensembles on this holdout.
- Do not retune against the 360 test questions and call that independent validation. An actual inference experiment with an old pinned LLM, independently isolated input and fresh events remains a useful next step.
