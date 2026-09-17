# Completed opposite-order HDR+ proxy evaluation

Both panels now cover all 20 frozen groups (100 frames each). The original
independent B evaluator resumed successfully and completed missing groups 18–20;
prior B1–17 judgments are unchanged. No main-context substitute or new candidate
inference was used. The [September 17 report](../2026-09-17-hdrplus-holdout/report.md)
remains the historical partial result and owns dataset/rubric/runtime details.
Panel A's raw responses there are unchanged; full B responses are recorded here.

| Metric | Final result |
| --- | --- |
| Missing groups | A: none; B: none |
| Exact preferred-set order agreement | 1/20 groups |
| Pairwise order agreement, ties included | 46/200 pairs |
| Order-stable strict preferences | 7; frozen minimum is 30 |
| Baseline top-1 preferred | A 6/20; B 2/20 |
| Baseline acceptable candidates rejected | A 30/59; B 38/65 |
| Explicit group keep coverage | A 20/20; B 20/20 |

| Candidate | A top-1 preferred | B top-1 preferred | A strict pairs correct | B strict pairs correct | Stable strict correct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 6/20 | 2/20 | 50/126 | 25/89 | 1/7 |
| TOPIQ_NR | 3/20 | 5/20 | 60/126 | 43/89 | 5/7 |
| MUSIQ | 5/20 | 6/20 | 67/126 | 48/89 | 4/7 |
| Optional refinement | 5/20 | 2/20 | 49/126 | 25/89 | 1/7 |

These references remain model-generated and strongly order-sensitive. They do not
establish human preference accuracy or calibrated false-reject rates. Completing
the missing judgments resolves the execution blocker, not the quality of the
reference. The promotion evidence gate still fails; no fusion, default model or
refinement change follows. Candidate scores were reused without rerunning models.
JSON validation checks all five IDs and all ten unique pairs per group, the
reversed-order mapping, preferred/acceptable subsets, and agreement totals.
