# Qwen and paired hybrid — frozen replay results

2026-11-24. Recovered from authenticated GitHub Actions job logs after Deep Research could not access scoring artifacts. Same 121 questions, 48 train / 32 validation / 41 test; **not independent replications**.

## Evidence

- Qwen run [45294059131](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45294059131), scoring job 138114160435, code commit `1cf6483fcdb7db1ad7e97478afffd5ed864ee841`. Model Qwen/Qwen2.5-0.5B-Instruct revision `7ae557604adf67be50417f59c2c2f167def9a775`.
- Inputs SHA-256 `80cc1d965c61e981f481c1902c385305903dfa5ab2f007f3cfa370c523d5597e`; frozen LLM predictions SHA-256 `6f9ea884274bbef139ef5fe7172659a0b9a972c327b5b3ebeaea9b193721adf0`; report artifact 14875787955, ZIP SHA-256 `61baed6a4278bf0f2f4be57c806308a30a1a438ee85ce58513aaf596d228bbbc`.
- Hybrid run [45294652819](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45294652819), job 138111861927, code commit `424faabc967cde616bd2687790ff228586493bb9`; numeric predictions SHA-256 `35353a117a21cbf6b94234696f677c0d15e32bfc05d747020f70cda88784d7e4`; report artifact 14875019492, ZIP SHA-256 `ee55ac4434d5175b5e031c721d2172e6711b73e6ad1128f702d7ff9722c39b16`.

## Scores

| Policy | Validation Brier | Test Brier |
|---|---:|---:|
| Neutral | .250000 | .250000 |
| Qwen direct | .247970 | .260797 |
| Qwen structured | .254981 | .254536 |
| Qwen selected (neutral fallback) | .250000 | .250000 |
| Numeric mean reversion (hybrid selected) | .220963 | .285148 |
| Blend 25% LLM | .225535 | .276777 |
| Blend 50% LLM | .231560 | .269929 |
| Blend 75% LLM | .239038 | .264602 |

Hybrid selected numeric-only on validation. Test gain versus half = -0.035148; descriptive nine-round bootstrap interval [-0.069250, 0.009349]. Qwen selected 50% fallback because direct validation gain fell below 0.005. Neither experiment demonstrated useful predictive superiority. Qwen raw probability is conditional Yes/No token softmax, not elicited event probability or full agentic forecasting. No model weights trained.

## Research direction

Deep Research completed a literature review, not new executions. Candidate next steps: point-in-time vintages (ALFRED), rolling-origin development, regularized priors with horizon-aware features, structured belief updates and independent prompt trajectories, logit aggregation and shrinkage. References: https://arxiv.org/abs/2604.18576 ; https://arxiv.org/abs/2506.21558 ; https://academic.oup.com/jrsssb/article/72/1/71/7076442 ; https://www.stlouisfed.org/publications/page-one-economics/2022/08/01/data-revisions-with-fred ; https://pubmed.ncbi.nlm.nih.gov/26250683/ .

Do not over-restrict exploration: consumed holdouts may be reused as development data, not new confirmatory evidence. Freeze candidate and comparators before an untouched grouped temporal test. Correlation, sparse observations and regime shift call for sensitivity analysis, not automatic exclusion. Prefer evidence of predictive improvement over adding architecture. No new experiment executed in the literature review or this reconciliation.

Decision: NO_CHANGE_REQUIRED on main; no promotion, no live submission, LOT01 unchanged.
