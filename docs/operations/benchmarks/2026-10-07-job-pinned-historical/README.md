# Complete historical score cohort comparisons

Two complete, job-pinned comparisons ran on the native Intel service at application
revision `76ec1db6b46b645c12b199989c12c29be38ecc56`. The serialization
[recovery](../../2026-10-07-job-pinned-streaming-recovery.md) removed whole-report
buffers; both reports completed under the original 4 GiB address-space,
600-second wall, 512 MiB report and 513 MiB wire limits. No measured peak-RSS or
latency improvement is claimed. The failed original namespace is retained.

## Verified historical facts

| Historical job date | Aug 28 | Aug 27 | Jul 16 |
| --- | ---: | ---: | ---: |
| Complete rows / finite scores | 40,620 | 40,620 | 40,620 |
| Grouping enabled in snapshot | Yes | Yes | No |
| Complete groups | 2,824 | 1,803 | 40,620 |
| Singleton groups | 652 | 272 | 40,620 |
| Maximum group size | 278 | 659 | 1 |
| Legacy review | 5,963 | 5,609 | 25,637 |
| Legacy reject | 34,657 | 35,011 | 14,983 |
| Legacy fallback | 667 | 313 | 20,671 |

All three cohorts have zero legacy keep, errors, unscored rows, written rows or
rank-accounting anomalies; all rows were historically simulated. Current
`quality_assessment` and `selection` facts are absent on every row. Historical
application revisions are unknown. These legacy decisions do not establish
current quality or selection outcomes.

Aug 28 versus Aug 27 pairs all 40,620 paths with identical finite scores. Five
configuration keys differ. Both snapshots enable grouping, so Aug 27 is not a
singleton baseline.

Jul 16 is a verified singleton baseline: grouping is disabled, every group has
one member and there are 40,620 groups. Relative to Aug 28, all 40,620 paths pair;
28,661 scores, 37,796 ranks and 19,866 legacy decisions differ. Of these decisions,
19,770 change from August reject to July review and 96 in the other direction.
The score delta **Jul 16 minus Aug 28** has P05 −0.69, median 0, P95 +0.79,
range −3.48 to +3.35 and mean +0.00163. Nineteen configuration keys differ,
including grouping, thresholds, backend parameters and reprocessing; disabled
embedding settings are among the differences and need not have affected execution.
Unknown historical code and these differences prevent a causal grouping,
current-policy A/B or photographic-quality improvement claim.

## Integrity and acceptance boundaries

The reports contain all rows, group members, rank diagnostics and available model
provenance. Report sizes are 249,897,224 and 261,880,341 bytes respectively.
An independent standard-library recomputation from private raw rows found zero
mismatches in aggregates, ranks, paired deltas and integrity receipts. Each
completed output was subsequently reused with no new application invocation.
Approved database/WAL/journal and configuration identities remained unchanged;
private permissions and receipt/report hashes were verified. The postdiagnostic
idle service, configuration and 40,620-record library snapshot are unchanged.

The diagnostic performs no preview decoding, inference, rescoring, photo/XMP write
or metadata migration. Private reports, per-photo paths, job/group identifiers,
source identities, full configurations and operator receipts remain outside the
public repository. [results.json](results.json) contains only allowed aggregates
and configuration key names. Resource caps are guards, not measured consumption.

Historical distribution accounting is complete. Current-policy real RAW/portrait
utility, independent directed-coverage G1/G2 references and optional MUSIQ resource
admission remain separate unmet gates. No default policy or model is promoted,
no additional historical rerun is needed, and annotation UI work remains closed.
