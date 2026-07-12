# Local Model Benchmark Report

- Manifest: `synthetic-local-baseline` version `1`
- Manifest SHA-256: `803184446eabd40d1b6dc818355f6405956ee8be77f845b2181402ddd9aa28cd`
- Items: 4
- Repeat count: 3
- Deterministic scores: True
- Images per second: 0.7981

## Quality Metrics

| Metric | Result |
| --- | --- |
| `group_top1` | 1/1 (1.000) |
| `pairwise_preference` | 3/3 (1.000) |
| `reject_recall` | 1/3 (0.333) |
| `scene_accuracy` | 4/4 (1.000) |
| `scene_other_rate` | 1/4 (0.250) |
| `screenshot_photo_separation` | 0.795714 |
| `quality_pairwise_preference` | 2/3 (0.667) |
| `aesthetic_pairwise_preference` | 2/3 (0.667) |
| `reject_prior_recall` | 2/3 (0.667) |
| `embedding_same_group_top1` | 2/2 (1.000) |
| `embedding_non_photo_photo_max_similarity` | 0.000483 |
| `face_recall` | 2/2 (1.000) |
| `face_accuracy` | 4/4 (1.000) |

## Item Scores

| Item | Group | Score | Scene | Mode |
| --- | --- | ---: | --- | --- |
| `portrait-sharp` | `portrait-burst-001` | 6.7471 | `people` | `hybrid` |
| `portrait-motion-blur` | `portrait-burst-001` | 6.6757 | `people` | `hybrid` |
| `low-light-room` | `low-light-001` | 4.6686 | `indoor` | `hybrid` |
| `ui-screenshot` | `non-photo-001` | 3.8729 | `other` | `hybrid` |
