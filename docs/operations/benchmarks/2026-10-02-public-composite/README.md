# Public composite diagnostic

The user authorized downloading several labeled public datasets on October 2,
2026 and combining them into a more demanding benchmark. This is a new bounded
acquisition scope. Historical acquisition budgets stay closed for their original
experiments. Production configuration, models, runtime state and photo metadata
are outside this scope.

## Corpus and native tasks

| Source | Downloaded component | Evaluation target |
| --- | --- | --- |
| [KonIQ-10k](https://database.mmsp-kn.de/koniq-10k-database.html) | 512×384 archive and crowd score distributions | Quality ranking against MOS; higher is better |
| [KADID-10k](https://database.mmsp-kn.de/kadid-10k-database.html) | Reference images, 25 distortions × 5 levels and crowd scores | Quality ranking against DMOS; the author's convention is higher is better |
| [Copydays](https://thoth.inrialpes.fr/~jegou/data.php.html) | Original gallery and strong modifications from the Meta VISSL mirror | Copy correspondence retrieval, with all original images retained in the gallery |
| [AlbumBench](https://github.com/byu-vision/albumbench) | Inventory, prompts, targets and official splits pinned to `20c3e1e5841398f702df77aaf28c08b5b327c5e7` | Retained query-conditioned tasks; images unavailable here and the current predictor is unsupported |

Copydays publisher links failed to connect in this environment. The downloaded
mirror is recorded in `sources.json`. Its correspondence rule matches
[VISSL's evaluation code](https://github.com/facebookresearch/vissl/blob/main/vissl/utils/instance_retrieval_utils/data_util.py):
numeric image filename divided by 100 identifies the source. This run includes
strong modifications only, without the full crop/JPEG suite or distractors.

AlbumBench's linked Hugging Face image host failed TLS connection after bounded
retries. Its metadata is included in the corpus inventory, with no fabricated
image predictions or metric. The release contains three task types; its paper's
headline counts and fourth task are not substituted for the actual inventory.
Six released rating targets repeat image IDs. Their original aligned values are
preserved and the inventory flags these anomalies; no deduplication or inferred
answer is applied.

The checksum-matching KonIQ archive contains 10,373 JPEGs, while the score table
contains 10,073 unique image names. All rated images are present. The 300 extra
images are retained locally and excluded from quality metrics; no scores are
invented for them. This source-release difference is recorded in the inventory.

## Frozen protocol

`protocol.json` was saved before scoring. It selects 1,024 records per quality
track by ascending SHA256 of stable item ID, and every available strong Copydays
query because that set is smaller than the limit. Every gallery original remains
available. This is a fixed diagnostic subset, with no training, calibration or
threshold fitting. It is not an official leaderboard evaluation or a blinded
independent test.

Quality uses the existing `AsyncLocalClient` heuristic mean across `VISION_DIMS`,
with learned model components disabled. This is a reproducible initial baseline,
not a measurement of the deployed NIMA/model stack. Copy retrieval uses 64-bit
pHash Hamming distance. Quality reports unfitted PLCC and SROCC; Copydays reports
top-1 and MRR with deterministic tie handling. Failures are counted explicitly.
Each track is reported separately; there is no combined scalar score.

MOS, DMOS, preference and copy labels do not establish directed important-content
coverage. These results cannot pass G1/G2, certify safe discard or promote an
algorithm into production. KADID reference-family and distortion identities are
preserved for later development/holdout experiments; a future learned comparison
must freeze a family-disjoint split before tuning.

## Initial measured result

The first run evaluated 1,024 KonIQ images, 1,024 KADID images and all 229 strong
Copydays queries against 157 originals (2,434 feature records). No predictions
or gallery images failed. Raw image inventory is 20,965, of which 20,584 enter
labeled tasks; 81 KADID references and 300 unrated KonIQ images remain separate.
All 25 KADID distortion types, five levels and 81 reference families are present
in the full corpus. Exact-byte cross-source duplicate count is zero; semantic
near-duplicate leakage was not established.

| Track | Baseline result |
| --- | --- |
| KonIQ quality | SROCC 0.3643; unfitted PLCC 0.3846 |
| KADID quality | SROCC 0.0694; unfitted PLCC 0.0746 |
| Copydays strong correspondence | Top-1 20.52%; MRR 0.2558; 87 queries have first-place ties |
| AlbumBench | 5,124 retained tasks; unsupported, no metric |

These results expose weak quality ordering on controlled distortions and limited
pHash robustness on strong modifications. They do not measure the deployed
learned scorer or official full benchmark. Per-distortion numbers in
`results.json` are exploratory diagnostics and must not become post-hoc test
categories for tuning. A subsequent comparison must freeze family-disjoint
splits and a predictor configuration before using these labels for improvement.

## Reproduce and recover

Download the exact artifacts listed in `sources.json` beneath an ignored root
such as `.local/public-benchmark-20261002`. Keep archives in `downloads/` and the
pinned AlbumBench metadata in `albumbench/`. For each download, use a `.part`
destination and `curl --fail --location --continue-at -`; rename to the final
filename only after a successful transfer and checksum validation. Preserve the
source attribution and original image-license restrictions; downloaded media
and raw labels are not redistributed in this repository.

The acquisition is bounded to 8 GB compressed and 15 GB expanded. The preparation
tool preflights all archives, rejects traversal, links, duplicate paths and
special files, checks native-label joins, then installs staged extraction
atomically. Per-image SHA256 values and archive receipts freeze the corpus.
Exact-byte cross-source duplicates are recorded as a diagnostic; this is not a
semantic near-duplicate audit.

```sh
uv run --no-sync python scripts/prepare_public_composite.py \
  --root .local/public-benchmark-20261002 \
  --output .local/public-benchmark-20261002/composite-manifest.json \
  --checkpoint .local/task-handoffs/culling-2026-10-02/composite-prepare.json

uv run --no-sync python scripts/benchmark_public_composite.py \
  --root .local/public-benchmark-20261002 \
  --manifest .local/public-benchmark-20261002/composite-manifest.json \
  --output .local/public-benchmark-20261002/baseline-1024 \
  --limit-per-track 1024
```

The runner saves each image's feature record and progress atomically. A repeated
command reuses valid records only when input bytes, manifest, configuration,
code and package versions match; corrupt records and failed predictions are
retried. The final identity includes selected input hashes. These checkpoints
and completed artifacts survive session or quota interruption without depending
on the final chat message.

Public `results.json` contains aggregate diagnostics, hashes and validation
evidence. Full manifests, targets, images, selected IDs and feature records stay
under the ignored local root. See the controller's current
[plan](../../2026-09-26-culling-improvement-plan.md#next-substantive-step-and-dispatch-boundary)
for the next decision.
