# Local Model Benchmark Report

- Manifest: `synthetic-local-baseline` version `1`
- Manifest SHA-256: `803184446eabd40d1b6dc818355f6405956ee8be77f845b2181402ddd9aa28cd`
- Items: 4
- Repeat count: 3
- Deterministic scores: True
- Images per second: 4.5874

## Quality Metrics

| Metric | Result |
| --- | --- |
| `group_top1` | 1/1 (1.000) |
| `pairwise_preference` | 3/3 (1.000) |
| `reject_recall` | 1/3 (0.333) |
| `scene_accuracy` | 1/4 (0.250) |
| `scene_other_rate` | 4/4 (1.000) |
| `screenshot_photo_separation` | 0.795714 |
| `quality_pairwise_preference` | n/a |
| `aesthetic_pairwise_preference` | n/a |
| `reject_prior_recall` | n/a |
| `embedding_same_group_top1` | 2/2 (1.000) |
| `embedding_non_photo_photo_max_similarity` | 0.485676 |
| `face_recall` | n/a |
| `face_accuracy` | n/a |

## Item Scores

| Item | Group | Score | Scene | Mode |
| --- | --- | ---: | --- | --- |
| `portrait-sharp` | `portrait-burst-001` | 6.7471 | `other` | `hybrid` |
| `portrait-motion-blur` | `portrait-burst-001` | 6.6757 | `other` | `hybrid` |
| `low-light-room` | `low-light-001` | 4.6686 | `other` | `hybrid` |
| `ui-screenshot` | `non-photo-001` | 3.8729 | `other` | `hybrid` |
