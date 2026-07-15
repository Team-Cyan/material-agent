# Aesthetic Label Store

The label store is available for future human review, but no personal labels or
production calibration profiles are created automatically.

Store labels in appdata, separate from the photo share:

```bash
material-agent aesthetic-labels \
  --database /config/labels/aesthetic-labels.sqlite \
  import --input labels.yaml --holdout-percent 20

material-agent aesthetic-labels \
  --database /config/labels/aesthetic-labels.sqlite stats

material-agent aesthetic-labels \
  --database /config/labels/aesthetic-labels.sqlite \
  export --split train --output calibration-train.yaml
```

Input items require `path`, `target`, `raw_score`, and either `human_score`
(1-10) or `human_rating` (1-5). Explicit `split: train|holdout` is preferred.
When absent, a stable path hash assigns the split so repeated imports cannot
silently move an item between train and holdout.

Imports are idempotent by photo path. The store never reads or writes XMP and
does not treat generated scores or model decisions as human labels.
