# Existing evaluator maintenance audit

Date: 2026-10-13. Source baseline: `ac651525ba82d4b6560153b8873c8fcab6b00c65`.

## Decision

Close A4 with **no extraction**. The audit found real duplication, but existing
helper chains already share substantial logic. The remaining small primitives
and near-duplicate bootstrap code do not justify changing frozen historical
runners, their source identities and recovery packages in this batch. This
uses the no-framework closure allowed by the
[A4 plan](2026-09-26-culling-improvement-plan.md).

This is a static maintenance audit, not a new benchmark or parity experiment.
No runner, test, protocol, cache, model, metric or production behavior changed.
The [local benchmark contract](../ai/modules/local-benchmark.md) continues to
keep native diagnostics separate from local scoring labels and production state.

## Inventory and existing reuse

All 17 `scripts/benchmark*.py` files were parsed with the repository interpreter;
the relevant helper bodies, imports, identity construction, cache validators,
resource guards and existing tests were inspected.

| Runners | Existing ownership and reuse |
| --- | --- |
| [hash hardcases](../../scripts/benchmark_hash_hardcases.py), [cooking hashes](../../scripts/benchmark_cooking_hashes.py), [direct coverage](../../scripts/benchmark_direct_coverage.py) | Historical report runners; cooking/direct coverage import `cooking_sequence_protocol`, and direct coverage imports `direct_coverage`. The hash/cooking runners require a new or empty output directory. |
| [coverage observability](../../scripts/benchmark_coverage_observability.py), [observability holdout](../../scripts/benchmark_observability_holdout.py), [representation control](../../scripts/benchmark_representation_control.py) | Reuse `direct_coverage`; holdout imports `evaluate_relation`, and representation control imports `controls`. Representation control owns its case identity, sealed records and resume verification. |
| [candidate graph](../../scripts/benchmark_candidate_graph.py) | Imports historical candidate/selection primitives from `direct_coverage`; constructed graph labels and bounded pair budgets remain a separate protocol. |
| [MobileCLIP candidate](../../scripts/benchmark_mobileclip_candidate.py), [Stanford40 actions](../../scripts/benchmark_stanford40_actions.py) | MobileCLIP uses the isolated local benchmark service; Stanford40 already imports its `sha256` and `peak_rss_bytes` helpers. Their quality/action acceptance tasks differ. |
| [public composite](../../scripts/benchmark_public_composite.py), [public NIMA](../../scripts/benchmark_public_nima.py), [public MUSIQ](../../scripts/benchmark_public_musiq.py), [public Copydays](../../scripts/benchmark_public_copydays.py) | NIMA imports composite; MUSIQ imports NIMA and uses its composite dependency; Copydays imports composite. Existing reuse includes atomic JSON, manifest/cohort validation, digest/read helpers, associations and parent-cache checks, as applicable to each runner. |
| [MUSIQ OpenVINO](../../scripts/benchmark_musiq_openvino.py), [OpenVINO full](../../scripts/benchmark_musiq_openvino_full.py), [native shapes](../../scripts/benchmark_musiq_native_shapes.py), [shared core](../../scripts/benchmark_musiq_shared_core.py) | Full/native shapes import the OpenVINO runner's hash, digest, safe IO and runtime isolation helpers. Shared core imports native shapes and reuses those helpers transitively, including `exact`, `peak_rss` and `check_resources`. |

## Candidate assessment

| Candidate and exact evidence | Assessment |
| --- | --- |
| `finite_number` in candidate graph; `finite` in native shapes and OpenVINO full | Identical AST bodies: exact built-in `int`/`float` types and finite values. One-line duplication; other prediction validators use `isinstance` with explicit boolean rejection and additional native constraints. No generic validator migration is justified. |
| Native shapes `hash_string` / OpenVINO full `hash_string`; native shapes `exact` | Both hash validators require 64 lowercase hex characters. `exact` compares the existing JSON digests and catches serialization errors; shared core already calls `native.exact`. Keep the frozen helper chain rather than create another dependency for these short predicates. |
| `peak_rss` in direct coverage/native shapes; `peak_rss_bytes` in MobileCLIP, representation control, public MUSIQ/Copydays and OpenVINO full | Several identical or equivalent conversions of process-lifetime `ru_maxrss` to bytes, with different integer conversion syntax. Stanford40/shared core already reuse an owner. Conversion is small; guard policy is not interchangeable: MUSIQ `process_budget` owns signals/timer/thread cleanup, native shapes `check_resources` distinguishes time/RSS errors, and full `check_budget` has a combined error. These are high-water observations, not current RSS. |
| NIMA `read_json` / Copydays `read_json`; OpenVINO `digest` / Copydays `digest_json` | Identical AST bodies for the bounded mapping reader and JSON digest. OpenVINO `read` instead applies symlink checks and a 16 MiB bound. Representation `canonical` uses compact separators; composite `digest` hashes bytes. A universal JSON/identity helper would erase meaningful contracts; the two small exact duplicates do not warrant revising frozen sources. |
| Public MUSIQ / OpenVINO full `resampling_units`, `draw_indices`, `paired_bootstrap` | Two real consumers of whole KADID families and KonIQ image IDs, retaining repeated-family multiplicity and paired indexes. This is the strongest future pure seam, but baseline scores arrive through different APIs; full exposes `correlation`, while public MUSIQ defines it internally. Metrics/report completeness and each native record remain runner-owned. No change is selected without a separately versioned need. |

## Identity, schema and recovery boundaries

A direct script hash covers that file's bytes; it does **not** cover a newly
imported helper's contents. Source maps below enumerate selected dependencies;
they are not a general recursive dependency closure.

| Evidence | Boundary retained |
| --- | --- |
| Composite `run`; NIMA `run`; Copydays `runtime_identity` / `preflight`; MUSIQ `source_hashes` / `run` | Composite/NIMA explicitly include their runner and selected application/helper files. MUSIQ additionally includes NIMA, composite and actually imported PyIQA module files. Copydays separately validates parent baseline sources and target runtime sources. Moving a helper requires adding it to every affected identity and frozen-file check. |
| OpenVINO `evaluate`; full `evaluate`; native shapes `evaluate`; shared core `frozen_sources` / `verify_sources` | Original parity evaluation has a direct `runner_sha256`. Full/native shapes include runner plus OpenVINO helper hashes. Shared core enumerates all three runner/native/helper files and pins the native/helper hashes before import. Rewriting native shapes also invalidates shared core's frozen dependency. |
| Representation `identity`; direct coverage `evaluate`; holdout `evaluate`; candidate graph `main` | Representation hashes runner, historical relation, observability and protocol assets. Other fingerprints are explicit selected files: holdout's direct runner hash does not transitively hash its imported `evaluate_relation`; candidate graph records the historical script hash. A new common helper must not be presumed covered by these existing fields. |
| Composite `valid_cached`; NIMA/MUSIQ `record_hash` / `reusable`; Copydays `validate_prediction` / `valid_cached`; OpenVINO/full/native shapes `valid_record`; representation `verified_record` | These are distinct schemas: heuristic score/pHash, NIMA distribution and its expectation, MUSIQ CPU/preprocessing evidence, normalized Copydays vectors, two parity scores, one full-corpus score, supported/unsupported shape records, and sealed geometry cases. Keep their validity decisions separate. |
| NIMA `record_hash`; MUSIQ `record_hash`; native shapes `native_record_hash`; representation `semantic_digest` | Observational-field exclusions differ: NIMA removes elapsed time, MUSIQ additionally removes RSS, native references have their own recipe, and representation hashes semantic results separately from sealed records. Other full-record digests retain observations. Changing JSON separators or field exclusions changes identity even with unchanged metrics. |
| OpenVINO/full/native shapes `evaluate`; MUSIQ `run`; representation `run`; shared core `fresh_output` | Valid atomic records resume under matching identities, with runner-specific recomputation and failure handling. Native shapes still compiles/readbacks graphs on resume, including unsupported records that cannot acquire a score. Shared core explicitly forbids prediction/report resume and requires fresh process outputs. A shared resume runner would change these contracts. |

## Conditional follow-up scope

Reopen this decision when a recurring resampling defect requires the same fix
in both consumers, or an authorized new protocol needs these same primitives,
and the maintenance benefit justifies migrating identities and recovery
packages. Start only with the public MUSIQ/full **pure resampling primitives**,
whose two consumers are shown above. Keep adapters for baseline access and all
protocol, IO, runtime, report and completeness logic with their current owners.
Do not retrofit historical records under the old identity.

Before such a change, freeze the old code and protocols; introduce explicit new
runner/package identities and enumerate the new helper in source identities,
transitive dependencies and in-run drift checks. Characterize complete semantic
outputs and exact seeded draw sequences for image/family units, repeated draws,
ties, empty/singleton/constant/nonfinite cohorts, invalid replicate counts and
intervals. Check that observational timing/RSS differences do not alter native
semantic hashes beyond each existing recipe.

Use `tests/test_public_musiq.py` and `tests/test_musiq_openvino_full.py` for the
two consumers. Add helper-only drift, unchanged-identity resume, changed-identity
cache rejection, interrupted/partial recovery, corrupt JSON/UTF-8, and time/RSS
guard cases. If the OpenVINO/native helper chain changes, also run
`tests/test_musiq_openvino.py`, `tests/test_musiq_native_shapes.py` and
`tests/test_musiq_shared_core.py`, and revise every affected frozen recovery
package explicitly. This is a future verification requirement, not an executed
test or approval for implementation.

## Audit verification

The report was self-reviewed against current function bodies and existing test
names; all relative Markdown links were checked. `git diff --check` and
`uv run --no-sync pytest -q tests/test_repository_boundary.py` passed
(3 tests). Runner-specific tests and performance/quality experiments were not
run because this batch changes documentation only. Historical identities and
runtime outcomes are preserved by leaving their sources untouched; this audit
does not newly verify live execution, throughput, memory improvement or quality.
