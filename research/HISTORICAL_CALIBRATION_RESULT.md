# Historical blind calibration — first frozen result

**Status:** completed and scored; no improvement admitted; no live deployment.

## Proof

- Code commit evaluated: `6c57d5d189d26803f784f32b92d48321669e88c6`.
- GitHub Actions run [45292706554](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45292706554), job `138105247852`: success for syntax/tests, data retrieval, calibration/evaluation and artifact upload.
- Archive: official ForecastBench processed forecast sets, 141,253,184 bytes, SHA-256 `3b3b9630f2ccf4da401e703266a116cdc7de535eabb4cb44c9a10d1c01315b0f`; 3,011 JSON files encountered; 6,258,262 rows read; 133,798 eligible rows before cohort/split selection; 349 cohorts.
- Complete aggregate [artifact 14874672657](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45292706554/artifacts/14874672657), ZIP SHA-256 from runner: `fe1febee7a240dd3fa6d4e9ca1e380196af3aad7befe317d74f15639c8b8e147`.
- Source: Forecasting Research Institute, ForecastBench, CC BY-SA 4.0; https://www.forecastbench.org/datasets/; Karger et al., ICLR 2025, https://arxiv.org/abs/2409.19839.

## Predeclared separation

Train forecasts before 2025-10-01; validation before 2026-02-01; test before 2026-07-01; evaluation label freeze 2026-10-01. Thirty-day label embargo for train and validation. Earliest forecast per model and source/event ID. Train/validation only for parameter fitting and choice. Test probabilities generated from p values alone before scoring. Four cohorts met training and validation coverage; two lacked test coverage.

## All selected cohorts

| Archived model variant | Train n | Validation n | Test n | Selected calibrator | Validation Brier before → after | Test Brier before → after | Status |
|---|---:|---:|---:|---|---|---|---|
| Claude 3.7 Sonnet zero-shot + frozen values | 234 | 215 | 0 | Identity | 0.043188 → 0.043188 | — | Insufficient test coverage |
| Claude 3.7 Sonnet zero-shot | 234 | 217 | 0 | Affine logit (a=-0.8, b=0.5) | 0.141659 → 0.099250 | — | Insufficient test coverage |
| GPT-4.1 zero-shot | 111 | 183 | 418 | Identity | 0.092783 → 0.092783 | 0.250478 → 0.250478 | NO_CHANGE_REQUIRED |
| GPT-4.1 zero-shot + frozen values | 109 | 178 | 419 | Identity | 0.050224 → 0.050224 | 0.160301 → 0.160301 | NO_CHANGE_REQUIRED |

Both scored GPT-4.1 configurations retained identity by the predeclared validation gate; held-out gain exactly zero. Their accuracy at 0.5 was 66.7464% and 78.5203%, respectively; these variants differ in input context and are not a controlled paired comparison. The 837 test observations are not necessarily 837 independent events because cohorts can overlap. The freeze-values variant can include historical community/market context; it is **not** an admissible proxy for our independent forecasting method.

The Claude validation gain is unconfirmed: no later holdout coverage; do not transfer its parameters.

## Decision

- **PASS:** executable historical experiment and mask/split checks.
- **NO_CHANGE_REQUIRED:** no fitted calibration deployed from this experiment.
- **UNKNOWN:** whether a learned correction improves our own model or live research agent.
- **BLOCK:** actual full-bot historical replay and first sandbox submission still require functioning model access; no LLM weight training took place.
- Never retune the first test set and then claim a new independent result. A subsequent experiment needs an untouched temporal cohort or prospective questions, and must use our bot's own archived forecasts before any production calibration.
- No LOT01 data or forecast transferred into the competition. No changes to live competition workflows or main.

## Next experiment

Evaluate the actual agent using question snapshots and pre-cutoff evidence only, with label files inaccessible to the forecasting process. A current model may know old outcomes from its weights: date filtering alone cannot prove absence of leakage. Use a pinned model with a training cutoff before the forecast date where possible, audit residual contamination, and confirm improvements prospectively on unresolved questions.
