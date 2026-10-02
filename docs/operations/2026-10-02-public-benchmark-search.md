# Public labeled photo benchmarks — October 2, 2026

The user explicitly requested an online search for standard test sets with
ground truth and published results. This step reviewed primary project pages,
papers and author repositories. No image archive was downloaded, benchmark
submission sent or model run performed. The earlier closed acquisition budget
does not prohibit this newly requested bibliographic search.

## Shortlist

| Benchmark | Available target and published result | Project fit and access evidence |
| --- | --- | --- |
| [Photo Triage / Automatic Triage for a Photo Series](https://pixl.cs.princeton.edu/pubs/Chang_2016_ATF/) | 15,545 photos / 5,953 series with human preferences. The [paper](https://pixl.cs.princeton.edu/pubs/Chang_2016_ATF/chang2016-triage-preprint.pdf) reports about 73% preference accuracy for VGG Siamese versus 57% for MemNet on high-agreement pairs, plus a series-level likelihood metric. | First choice for within-series ranking. Official project links the benchmark; the old download host was inaccessible through the search tool. [CodaLab](https://competitions.codalab.org/competitions/9621) remains readable and requires login for participation. Downloadability is not confirmed. |
| [AlbumBench](https://byu-vision.github.io/albumbench/) | Album-specific intent selection, rating and grouping targets with published multi-model comparisons. [Author repository](https://github.com/byu-vision/albumbench) describes 641 albums, 26,973 image records, 5,124 tasks and 508 train / 133 test albums. | Useful for content/context diagnostics. The paper/project describes 27,051 images and four tasks, while the released snapshot lists three task types. Pin the actual release and check completeness before execution. [Linked image release](https://huggingface.co/datasets/Shawn-Huang/CUFED-AlbumBench) is labeled CC-BY-NC-2.0. |
| [KonIQ-10k](https://database.mmsp-kn.de/koniq-10k-database.html) | 10,073 real-world images with crowd MOS/distributions. The author reports KonCept512 SROCC 0.921 on KonIQ and 0.825 on LIVE-in-the-Wild. | Direct quality-ranking diagnostic; not redundancy labels. Author page links images/scores. [University archive](https://darus.uni-stuttgart.de/dataset.xhtml?persistentId=doi%3A10.18419%2Fdarus-2435) lists a 731.4 MB 512×384 archive and public scores. Image-specific source licenses still apply. |
| [MFND](https://similarity.cs.st-andrews.ac.uk/mfnd/) | Downloadable identical, manipulated-copy IND and non-identical NIND cluster labels, linked to the 2019 near-duplicate benchmark paper. | Real near-duplicate candidate diagnostic. The site explicitly says NIND is generally not an equivalence relation and notes anomalies. Cluster membership cannot establish directed safe rejection. Source images belong to MIR-Flickr and require separate retrieval/terms checks. |
| [DISC21 / ISC2021](https://ai.meta.com/datasets/disc21-dataset/) | Copy-to-source ground truth and distractors. [Author code](https://github.com/facebookresearch/isc2021) provides instructions to reproduce the paper's baselines. | Useful for copy matching/candidate retrieval, not semantic completeness. Official scale is one million reference images and 50,000 queries per development/test set; full media is about 350 GB. A small diagnostic subset cannot claim the full benchmark's result. |

## Review limits

Photo Triage preserves preference uncertainty, but its released training/validation
labels differ from the server-held test labels. The paper's reported split counts
do not sum to its headline series total; use actual release metadata rather than
reconstructing splits from prose. It also filtered extremely similar burst frames
during collection. Its preference target therefore cannot certify preservation
of every distinct action or important region.

AlbumBench's labels depend on a user query. They cannot be used to penalize a
pipeline that was never given that query. The current release inventory also
needs reconciliation with the paper before a comparable run is claimed.

[BuIQA](https://arxiv.org/html/2511.07958v1) is another relevant paper, but its
BI-OQA targets are downstream-model/PSNR effects, while BI-SQA reuses Photo Triage
and SPAQ judgments. Its entire annotation count is not independent human gold.
A standalone downloadable release was not established in this search; it is
not the first execution candidate.

Live metadata follow-up confirmed AlbumBench's README counts at repository
commit `20c3e1e5841398f702df77aaf28c08b5b327c5e7`. A bounded request to Photo
Triage's HTTP download page returned 503; its HTTPS project request failed TLS
in this environment. This is an access limitation observed here, not proof that
the data is unavailable everywhere. No authenticated competition operation was
attempted.

Published numbers above are author results under their own protocols, not
material-agent measurements or directly comparable cross-dataset scores.

## Next executable scope

First resolve Photo Triage's actual image/label retrieval and dataset terms. If
that remains unavailable, KonIQ has the clearest verified public artifact listing
for a quality-only diagnostic. Freeze source version, checksums, official splits,
score direction, ties, missing outputs and metrics before running the existing
scorer. Use native targets; do not translate preference or MOS into cover edges.
Check the scorer's training-data exposure before claiming independent test results.

An existing-scorer ranking/quality diagnostic can use these standard targets
without inventing new annotation work. Any later culling experiment still needs
independent directed important-content coverage evidence under G1/G2. This search
does not pass those gates, authorize a new acquisition volume, select new models
or change production defaults. Next work is a bounded source-access/metadata
verification step; bulk image acquisition and evaluation remain separate scopes.
