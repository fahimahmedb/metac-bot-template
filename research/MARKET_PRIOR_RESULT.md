# New-source market calibration — frozen result
2026-11-24. Research only; not an approved live tournament input.
First attempt 45299025971 (454bd4a275e1e42d5c3429fdd93a76e0bd815a1a) failed at preparation: 44 development cases, 188 test cases. No fit or score. Expanded development sources only, retained 188 Kalshi held-out cases. Repaired code add7297e8bafe03f3b8dbfb3b57753b8195d23fa.
Successful run [45299264032](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45299264032), exact code SHA 5752b6a49c4d0086fab2c594967c9cdb26d82e60. Jobs prepare 138127390996, fit 138127793128, score 138128026583 all success. Archive SHA256 3b3b9630f2ccf4da401e703266a116cdc7de535eabb4cb44c9a10d1c01315b0f; snapshot commit 86b92ba06ed34d606d633bff3e99af54dd447d3a. 40 snapshots, 7,506,694 archive rows scanned, 4,015 candidate events, 1,826 development, 1,412 final train, 188 test (Kalshi only, 5 rounds, 47.34% YES). Development: INFER 44, Manifold 318, Metaculus 218, Polymarket 1246. Inputs SHA256 2f3294f7ed6d527afe444fda5d3d794c1ae7517eef747396a7aadab49ee9094d; frozen predictions SHA256 11f64655bca6a4284e7c8d954bccb1108537f7f884bd253e8c9bd06e21878452; score artifact 14877647945 digest 60407d4d6470276dbeebd3a52860b7b0d10f3a0d5036b68ee4f5595f4d247dcd.
| Policy | Mean rolling validation Brier | Test Brier |
|---|---:|---:|
| Market | .117456 | .123497 |
| Neutral | .250000 | .250000 |
| Shrink 10% | .118695 | .126832 |
| Shrink 25% | .125561 | .135716 |
| Extremize | .119494 | .122371 |
| Temperature | .117545 | .123497 |
| Affine (selected) | .112545 | .126091 |
| Context LR | .120089 | .146963 |
| Context blend | .115728 | .126375 |
Selected affine improved over neutral by .123909 (49.56% relative), but lost .002594 versus raw market (round-bootstrap 95% CI [-.006134,.000595]); its threshold accuracy 83.51% vs market 80.32% does not override Brier/log loss (0.388956 vs 0.382815). Extremizing showed a descriptive .001127 Brier gain vs market but was NOT selected in validation; no confirmatory claim. Only 5 test rounds, cross-platform transfer and resolved-case selection limit inference. Market information already contains forecasts from other participants, so improvement over neutral is not evidence of independent agent skill. No odds-based method promoted; raw market is a strong research comparator, not approved for FutureEval. No additional retuning on consumed test. Decision NO_CHANGE_REQUIRED on official bot; next materially different experiment requires richer point-in-time evidence, or fresh independent forecast outputs with a suitably qualified model. Prior negative rolling economic result preserved. No LOT01 data or competition submission used.
