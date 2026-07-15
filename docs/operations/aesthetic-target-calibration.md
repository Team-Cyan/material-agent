# Target-Specific NIMA Calibration

## Purpose

The bundled NIMA model produces a general 1-10 expected aesthetic rating. It
does not know this operator's preferences and is not target-specific by itself.
`material-agent` therefore keeps the raw NIMA score and applies an optional,
versioned affine profile only when enough human labels exist.

The runtime profile order is:

1. exact primary object label, such as `person` or `dog`;
2. normalized scene, such as `people` or `animals`;
3. `default`.

An exact-object adjustment is blended by detection confidence. An undertrained
exact profile falls back to a trained scene/default profile. If no profile has
`minimum_label_count` labels, calibration is an explicit no-op.

## Label File

Use ratings made by a human reviewer. Do not reuse `mj:score`, generated XMP
ratings, or the model's own keep/review/reject decisions as ground truth.

```yaml
items:
  - path: example-001.ARW
    target: person
    raw_score: 6.17
    human_rating: 4
  - path: example-002.ARW
    target: person
    raw_score: 5.82
    human_score: 7.5
```

`human_rating` is a 1-5 star rating and is mapped to 2-10. `human_score` is an
explicit 1-10 value. `path` is optional provenance; the fitter requires
`target`, `raw_score`, and one human rating field.

Collect at least 20 labels per target from independent shoots, lighting, and
cameras. Keep a separate holdout set; the fitting report measures training
error and must not be treated as holdout evidence.

## Fit Profiles

```bash
material-agent fit-aesthetic-calibration \
  --labels labels.yaml \
  --output calibration.yaml \
  --report calibration-report.json \
  --minimum-label-count 20 \
  --minimum-raw-span 1.0 \
  --policy-version personal-aesthetic-2026-07-v1
```

The command constrains scale to `0.5-1.5` and offset to `-2.0-2.0`. A profile
must also cover the configured raw-score span and reduce RMSE versus unmodified
NIMA; unidentifiable or non-improving profiles are omitted. It exits with status
2 when no target passes these gates. Copy the generated
mapping under `local.aesthetic.calibration`, review the diff, and run a dry-run
rescore or full scoring pass before deployment.

`benchmark-local` uses the effective calibrated NIMA score when a calibration
profile is configured and reports its pairwise aesthetic accuracy separately
from technical-quality aggregates.

## Runtime and Rescore Behavior

Each fresh score artifact records:

- `aesthetic.score`: raw NIMA expected value;
- `aesthetic_calibration.raw_score` and `effective_score`;
- selected target/profile, detection confidence, policy version, fit
  parameters, label count, and whether calibration was applied;
- persisted `overall_aesthetic_raw` and effective `overall_aesthetic` signals.

`rescore` can rebuild the effective score from the persisted raw signal, but
the signal table does not retain object detections. It therefore uses the
scene/default profile. Run the full dry-run pipeline when exact-object profile
selection must be re-evaluated.

Subject-crop NIMA is intentionally not enabled. Cropping can discard global
composition and doubles aesthetic inference. It should be promoted only after
a labelled whole-frame-versus-crop ablation improves an independent holdout.
