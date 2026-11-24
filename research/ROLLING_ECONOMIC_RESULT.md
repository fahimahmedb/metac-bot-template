# Rolling economic learning — frozen outcome
2026-11-24. Research only.
Run [45298118173](https://github.com/fahimahmedb/metac-bot-template/actions/runs/45298118173), SHA 7dac00ba3a847d655deef5a2c870385cfc840b27; prepare 138123565460, fit 138123986073, score 138124182568 all success. 16 tests passed.
Archive SHA256 3b3b9630f2ccf4da401e703266a116cdc7de535eabb4cb44c9a10d1c01315b0f; snapshot commit 86b92ba06ed34d606d633bff3e99af54dd447d3a; input SHA256 1ae9cacd1c0f1c450ac9284dd4e7b8957090ae70fd31d7577fd6a80135f4f22e; frozen predictions SHA256 ae34fb7628b76ab60f74dc690acaa39ebeff36caafb6de1c2ca19326d265b13d; scoring artifact 14877756306 digest 0aa093da024eb3f9b549d263a13f83bc23da0892cbea77d16a75d97927490338.
7,506,694 archive rows scanned, 7,722 eligible cases, 6,194 development, 5,624 final train; 500 test observations across 142 series and 9 rounds, 121 previous replay series excluded. Test YES 48.2%; 264 seven-day, 236 thirty-day.
| Policy | Mean rolling validation Brier | Test Brier |
|---|---:|---:|
| Half (selected) | .250000 | .250000 |
| Empirical (best simple) | .248941 | .256531 |
| Momentum | .271332 | .259311 |
| Mean reversion | .249479 | .261786 |
| Recent | .253935 | .257880 |
| Pooled | .259602 | .267991 |
| LR .03 | .307030 | .312002 |
| LR .3 | .326293 | .314747 |
| LR 3 | .330778 | .315069 |
| HGB 3 | .303155 | .273414 |
| HGB 7 | .305414 | .273551 |
| LR .3 shrink | .275226 | .270655 |
| HGB 3 shrink | .271163 | .259314 |
The validation policy selected half by predeclared .002 margin. No candidate beat neutral on test. Neutral vs empirical gain .006531, round bootstrap CI [-.002569,.016105], series bootstrap [-.004136,.017016]. Repeated horizons/series and shared rounds not independent; bootstrap intervals separate rather than joint. Sparse frozen values are proxies, not complete real-time vintages; no conclusion about all time series methods. All 500 test cases now consumed. NO_CHANGE_REQUIRED for production. PARK sparse-snapshot economic model family until material new evidence, not endless parameter search. Next: richer historical market context as a separately evaluated reference, respecting competition rules; independent new source cohort if available. LOT01 not used.
