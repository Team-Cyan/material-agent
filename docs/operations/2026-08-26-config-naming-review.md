# Configuration Naming Review

Date: 2026-08-26

## Scope

This review covers the public keys in `config.yaml`, the Intel OpenVINO image
profile, normalized defaults, and the supported Ollama/oMLX compatibility
sections. Repeated scene, metric, calibration-profile, and model-profile keys
are represented with `*` wildcards.

The current base configuration has 211 leaf values. The main problem is not
individual spelling; runtime, model, pipeline, score-policy, selection, and
output concerns are mixed at the same level. A versioned schema migration is
safer than renaming isolated keys one at a time.

## Recommended Top-Level Shape

```yaml
schema_version: 2

runtime:          # backend selection, availability contract, logging
library:          # input file types; input path remains a CLI/task argument
models:           # detection, semantic, quality, aesthetic, embedding, face
pipeline:         # RAW preview, grouping, prefiltering, work windows
score_policy:     # signals, fusion, scene profiles, thresholds, decisions
output:           # language, commentary, XMP behavior
model_registry:   # installed-model discovery and selection
compatibility:    # explicitly quarantined Ollama/oMLX settings
```

## Immediate Findings

These are correctness or false-configurability problems, not cosmetic naming
preferences.

| Current path | Finding | Recommended action |
| --- | --- | --- |
| `screening_policy.top1_review_fallback` | Group-selection behavior is stored under screening and previously ran even when grouping was disabled. | Move to `pipeline.grouping.best_candidate_review.enabled`. Gate it on `pipeline.grouping.enabled`. |
| `scoring.pixel_weight`, `scoring.vision_weight` | Legacy paths, now stripped during normalization. They previously controlled only a non-authoritative diagnostic total. | Completed: removed the diagnostic aggregate and retained the layered summary as the only total. |
| `scoring.cache_revision` | Changes cache identity but its name suggests score behavior. | Move to `score_policy.revision`. |
| `grouping.group_guard.*` | No production consumer calls `GroupGuard`; the keys are inert. | Remove until a tested policy owns them. |
| `focus_integrity.high_resolution_roi` | Normalized and validated, but does not control RAW decoding or focus analysis. | Remove or wire it; prefer `pipeline.raw_preview.focus_max_edge_pixels` as the actual control. |
| `portrait_face_eye.min_face_ratio` | Normalized but never consumed. | Remove or implement under a defined portrait-focus policy. |
| `portrait_face_eye.review_penalty` | Normalized but never consumed; the actual keep-to-review threshold is fixed in code. | Replace with an explicit threshold only if the policy becomes configurable. |
| `xmp.compatibility_profile` | Normalized but never consumed. | Remove until more than one implemented profile exists. |
| `xmp.write_mode` | Only `sidecar` is accepted. | Remove false configurability; keep sidecar as an invariant. |
| `xmp.machine_tag_target` | Only `identifier` is accepted. | Remove false configurability or implement another tested target. |
| `preview.fallback_decode` | Only `half_size` is accepted and decode does not branch on it. | Remove until another mode exists. |
| `scene_weights` | Legacy input is transformed into `scene_profiles` and removed from normalized/cache state. | Completed for v1; move the canonical shape to `score_policy.scene_profiles` with the versioned v2 migration. |

Implemented bridge: v1 now stores this selection rule canonically at
`grouping.best_candidate_review.enabled`; the old
`screening_policy.top1_review_fallback` path is accepted only as an input alias,
is removed from normalized snapshots, and conflicts are rejected. A later v2
migration can move the stable inner shape to
`pipeline.grouping.best_candidate_review.enabled` with the rest of `grouping`.

Removed inert v1 fields: `grouping.group_guard.*`,
`focus_integrity.high_resolution_roi`, `portrait_face_eye.min_face_ratio`, and
`portrait_face_eye.review_penalty`. The normalizer also strips these legacy
inputs so they no longer affect persisted snapshots or cache identity. The
actual focus preview bound remains `preview.focus_max_size`.

Removed fixed-value aliases from canonical v1 output:
`preview.fallback_decode`, `xmp.write_mode`, `xmp.compatibility_profile`, and
`xmp.machine_tag_target`. Their only supported values remain accepted as legacy
input and are stripped during normalization; unsupported values still fail
closed. RAW fallback remains half-size demosaic, XMP remains sidecar-only, and
machine tags remain in `xmp:Identifier` as code-level invariants.

Removed the non-authoritative aggregate score path and its
`scoring.pixel_weight` / `scoring.vision_weight` controls. Normal, prefilter
reject, and hard-reject results now all use the same layered total. Public
configuration uses `scene_profiles`; legacy `scene_weights` remains an input
alias but is removed from normalized snapshots and cache identity.

## Core Runtime and Library Names

| Current path | Recommendation | Rationale |
| --- | --- | --- |
| `backend` | `runtime.backend` | `backend` is too generic at the document root. |
| `legacy.enabled` | `compatibility.legacy_backends_enabled` | State what is being allowed. |
| `log_level` | `runtime.logging.level` | Associate the value with runtime logging. |
| `input_dir` | Remove from durable config | The run/Web task input root is operational state and already supplied separately. |
| `reprocess` | Remove from durable config | It is a per-run cache-bypass option, not stable scoring policy. |
| `raw_extensions` | `library.raw_extensions` | Associate discovery rules with the library. |
| `output_language` | `output.language` | Associate the language with generated output. |
| `commentary_enabled` | `output.commentary.enabled` | Avoid a root-level feature toggle. |

## Model and Inference Names

Use `models` for individual model roles and `runtime.inference_defaults` only
for inherited values. Per-model values override defaults.

| Current path | Recommendation | Rationale |
| --- | --- | --- |
| `local` | `models` | `local` describes deployment location, not the contained model roles. |
| `inference.runtime` | `runtime.inference_defaults.provider` | `runtime` currently means OpenVINO/Transformers/CPU inconsistently. |
| `inference.device` | `runtime.inference_defaults.device` | Make inheritance explicit. |
| `inference.fallback_device` | `runtime.inference_defaults.fallback_device` | Make inheritance explicit. |
| `inference.model_cache_dir` | `runtime.inference_defaults.model_cache_dir` | It is a default inherited by models. |
| `inference.provider_tags` | `runtime.provenance_tags` | Tags are provenance, not execution controls. |
| `inference.enforce_available` | `runtime.inference_defaults.required` | `required` describes fail-fast behavior directly. |
| `local.*.enabled` | `models.*.enabled` | Keep the conventional toggle. |
| `local.*.enforce_available` | `models.*.required` | Shorter and clearer fail-fast contract. |
| `local.*.runtime` | `models.*.provider` | Avoid overloading the word runtime. |
| `local.*.model_name` | `models.*.model_id` | It is an implementation/model identifier, not a display name. |
| `local.*.model_version` | `models.*.artifact_version` | Distinguish packaged artifact versions from source revisions. |
| `local.embedding.model_revision` | `models.embedding.source_revision` | It is specifically an immutable upstream revision. |
| `local.*.model_path` | `models.*.artifact_path` | Match the packaged artifact terminology. |
| `local.embedding.processor_path` | Keep | The meaning is specific and clear. |
| `local.*.compiled_cache_dir` | `models.*.compiled_model_cache_dir` | Distinguish compiled-model cache from result cache. |
| `local.*.result_cache_size` | `models.*.result_cache_max_entries` | State the unit and bound. |
| `local.*.performance_hint` | `models.*.openvino.performance_hint` | This is provider-specific. |
| `local.*.batch_size` | `models.*.openvino.batch_size` | This is provider-specific. |
| `local.*.infer_requests` | `models.*.openvino.infer_request_count` | State that this is a count; allow `auto`. |
| `local.*.max_in_flight` | `models.*.openvino.max_infer_request_count` | It caps resolved infer requests, not arbitrary pipeline work. |
| `local.embedding.allow_batch_fallback` | `models.embedding.openvino.allow_single_item_fallback` | State the actual fallback behavior. |
| `local.semantic.pretrained` | `models.semantic.pretrained_variant` | Clarify that it identifies a weight variant. |
| `local.semantic.min_confidence` | `models.semantic.min_classification_confidence` | Identify the classified signal. |
| `local.detection.score_threshold` | `models.detection.min_object_confidence` | Avoid a generic score threshold. |
| `local.detection.face_score_threshold` | `models.detection.min_face_confidence` | Use the same confidence vocabulary. |
| `local.detection.input_size` | `models.detection.input_edge_pixels` | State the unit and square-input assumption. |
| `local.detection.max_results` | `models.detection.max_detections` | State what is counted. |
| `local.face.model_asset_path` | `models.face.artifact_path` | Align model asset naming. |
| `local.face.num_faces` | `models.face.max_faces` | It is an upper bound. |
| `local.face.min_detection_confidence` | `models.face.min_confidence` | Detection is already established by the model role. |
| `local.quality.policy_version` | `models.quality.normalization_policy_revision` | It versions normalization/role policy, not the model. |
| `local.quality.metrics.*.lower_better` | `models.quality.metrics.*.lower_is_better` | Read as an unambiguous boolean statement. |
| `local.quality.metrics.*.raw_min/raw_max` | `models.quality.metrics.*.input_range.min/max` | Group the normalization range. |
| `local.quality.metrics.clipiqa+` | `models.quality.metrics.clipiqa_plus` | Avoid punctuation in configuration paths. |

## Calibration Names

| Current path | Recommendation |
| --- | --- |
| `local.aesthetic.calibration.enabled` | `models.aesthetic.calibration.enabled` |
| `...policy_version` | `...policy_revision` |
| `...minimum_label_count` | `...min_labels` |
| `...minimum_target_confidence` | `...min_target_confidence` |
| `...pivot` | `...score_pivot` |
| `...profiles.*.scale` | Keep |
| `...profiles.*.offset` | Keep |
| `...profiles.*.label_count` | Keep |

## Pipeline Names

| Current path | Recommendation | Rationale |
| --- | --- | --- |
| `preview` | `pipeline.raw_preview` | It is specifically the RAW-to-raster boundary. |
| `preview.prefer_embedded` | `pipeline.raw_preview.prefer_embedded_jpeg` | State which embedded representation is preferred. |
| `preview.max_size` | `pipeline.raw_preview.scoring_max_edge_pixels` | State purpose and unit. |
| `preview.focus_max_size` | `pipeline.raw_preview.focus_max_edge_pixels` | State purpose and unit. |
| `preview.jpeg_quality` | `pipeline.raw_preview.jpeg_quality` | Keep within the clearer namespace. |
| `grouping.enabled` | `pipeline.grouping.enabled` | Keep the feature name. |
| `grouping.time_gap_seconds` | `pipeline.grouping.max_capture_gap_seconds` | Describe the split condition. |
| `grouping.visual_similarity.hash_threshold` | `pipeline.grouping.visual.max_hash_distance` | State direction and distance meaning. |
| `grouping.visual_similarity.max_merge_gap_minutes` | `pipeline.grouping.visual.max_capture_gap_seconds` | Use one time unit and state the boundary. |
| `grouping.embedding_similarity.threshold` | `pipeline.grouping.embedding.min_cosine_similarity` | State direction and metric. |
| `screening` | `pipeline.prefilter` | It is an optional early inference gate, not final selection policy. |
| `screening.tier1_threshold` | `pipeline.prefilter.min_technical_score` | State what tier 1 compares. |
| `screening.tier2_threshold` | `pipeline.prefilter.min_model_prior` | State what tier 2 compares. |
| `screening.musiq.score_divisor` | `pipeline.prefilter.musiq.output_scale` | The value normalizes model output; it is not a mathematical divisor policy. |
| `review_pipeline.score_prefetch_window` | `pipeline.review.prepared_item_window` | It bounds prepared scoring work, not only model prefetch. |
| `review_pipeline.max_files` | `pipeline.review.max_files` | Keep as a pilot/task limit. |

## Focus and Technical Signal Names

| Current path | Recommendation | Rationale |
| --- | --- | --- |
| `focus_integrity` | `score_policy.focus` | It controls focus measurement and rejection policy. |
| `focus_integrity.mode` | `score_policy.focus.measurement_mode` | State what the mode selects. |
| `focus_integrity.downscale_warning_ratio` | `score_policy.focus.warn_above_downscale_ratio` | State threshold direction. |
| `focus_integrity.roi_expand_ratio` | `score_policy.focus.subject_roi_expand_ratio` | State which ROI is expanded. |
| `focus_integrity.eye_roi_ratio` | Keep within `score_policy.focus`. |
| `focus_integrity.global_blur_reject_below` | `score_policy.focus.catastrophic_blur_score_below` | Match the recorded rejection reason. |
| `portrait_face_eye.enabled` | `score_policy.focus.portrait_review.enabled` | It is selection/focus policy, not a model definition. |
| `scorers.exposure.*` | `score_policy.technical.exposure.*` | These are technical-signal controls. |
| `scorers.sharpness.*` | `score_policy.technical.sharpness.*` | These are technical-signal controls. |
| `scorers.subject/composition/lighting/color/clarity/depth/mood.enabled` | `score_policy.aesthetic_dimensions.*.enabled` | They are backend dimensions, not independent scorer objects. |
| `scorers.*.weight/min_score` | Remove or place under an explicitly authoritative fusion policy. | Current layered final scoring does not consume these as advertised. |
| `scorers.exposure.overexpose_threshold` | `score_policy.technical.exposure.highlight_soft_scale` | It scales scene-profile cutoffs rather than acting as one absolute threshold. |
| `scorers.exposure.overexpose_hard_limit` | `score_policy.technical.exposure.highlight_hard_scale` | It is a multiplier, not a hard limit value. |
| `scorers.exposure.underexpose_threshold` | `score_policy.technical.exposure.shadow_soft_scale` | It scales scene-profile cutoffs. |
| `scorers.exposure.underexpose_hard_limit` | `score_policy.technical.exposure.shadow_hard_scale` | It is a multiplier, not a hard limit value. |
| `scorers.sharpness.min_variance/max_variance` | `...laplacian_variance_range.min/max` | Group the unit-bearing normalization range. |

## Score and Selection Policy Names

| Current path | Recommendation | Rationale |
| --- | --- | --- |
| `decision_policy` | `score_policy.decisions` | Decisions are part of the authoritative score policy. |
| `decision_policy.keep_threshold` | `score_policy.decisions.keep_score_at_or_above` | Encode comparison direction. |
| `decision_policy.review_threshold` | `score_policy.decisions.review_score_at_or_above` | Encode comparison direction. |
| `decision_policy.hard_reject.technical_quality_below` | `score_policy.decisions.reject_if.technical_quality_below` | Read as a rule. |
| `decision_policy.hard_reject.subject_focus_below` | `score_policy.decisions.reject_if.subject_focus_below` | Read as a rule. |
| `screening_policy.weight` | `score_policy.fusion.screening_prior_weight` | It affects final fusion, not prefilter execution. |
| `scene_profiles.*.aesthetic_weights` | `score_policy.scene_profiles.*.aesthetic_dimension_weights` | Make the weighted values explicit. |

## Output and Model Registry Names

| Current path | Recommendation |
| --- | --- |
| `xmp` | `output.xmp` |
| `model_management` | `model_registry` |
| `model_management.selection_enabled` | `model_registry.apply_selections` |
| `model_management.registry_dir` | `model_registry.root_dir` |
| `model_management.catalog_path` | `model_registry.catalog_path` |

## Ollama and oMLX Compatibility Names

These backends are explicitly quarantined and should not drive the v2 core
schema. Place them below `compatibility.backends.ollama` and
`compatibility.backends.omlx` while retaining their backend-specific vocabulary.

Keep these names unless their implementation changes:

- Ollama: `base_url`, `vision_model`, `fast_vision_model`,
  `commentary_model`, `timeout_seconds`, `max_concurrent_requests`.
- oMLX runtime: `required_version`, `require_structured_outputs`,
  `require_xgrammar`, `probe_on_run`, `enforce_dedicated_instance`.
- oMLX requests: schema names, `contract_mode`, `prompt_preset`,
  `model_profile_mode`, `enable_thinking`, `temperature`, `xtc_probability`.
- oMLX admin: endpoint/model identifiers, instance/model directories, cache
  toggle, retries, token limits, image edge, and JPEG quality.

The current oMLX normalizer mirrors grouped `admin` values back into flat keys.
That dual representation should be accepted only as a v1 input alias; v2 output
and persisted snapshots should contain the grouped representation once.

## Migration Strategy

1. Add `schema_version: 2` and one canonical v2 normalizer.
2. Accept v1 keys as read-only aliases for one release cycle and emit explicit
   deprecation diagnostics with the replacement path.
3. Reject configurations that specify both an old and new path with different
   values; never choose silently.
4. Persist only canonical v2 snapshots and build score-cache identity from the
   canonical representation.
5. Remove inert keys before tuning values. Do not calibrate thresholds against
   settings that the authoritative score does not consume.
6. Validate v2 on a labelled benchmark and a bounded NAS dry-run before any
   full-library rerun or XMP write.
