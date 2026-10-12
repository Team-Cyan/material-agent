"""Characterize finalization before selection and terminal writer projection.

Decode, model and metadata I/O are replaced with in-memory collaborators. Full
payload expectations also cover keys the runtime does not own and nested aliases.
"""

import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from material_agent.adapters.metadata import exiftool_xmp as xmp
from material_agent.app import review_runtime
from material_agent.domain.evidence_refinement import refine_group
from material_agent.domain.scoring_engine import ScoreBundle


GROUP_COMMENT = "Group issues: soft.\nShooting advice: steady."
POST_COMMENT = "Post advice: light sharpening."
UNKNOWN_EYES = {
    "version": 1,
    "status": "unknown",
    "value": None,
    "source": "unavailable",
    "reason": "no_reliable_eye_measurement_or_context",
}


def payload():
    return {
        "score_total": 5.0,
        "scores": {"sharpness": 5.0},
        "meta": {"focus_preview_size": [16, 16], "private": {"retained": True}},
        "scene": "people",
        "scene_raw": "baseline scene",
        "instructions": "baseline instructions",
        "boosted": True,
        "decision": "review",
        "decision_reasons": ["baseline reason"],
        "screening_prior": 0.5,
        "visible_breakdown": {},
        "policy_version": "baseline-policy",
        "signals": [{"source": "baseline"}],
        "skip_write": True,
        "previous_group_info": {"group_id": "g", "group_rank": 1, "group_size": 1},
        "custom": {"retained": True},
        "group_commentary": "old commentary",
    }


def selected(original, *, keep=False, commentary=""):
    """Expected complete quality/selection record, independent of domain calls."""
    return {
        **original,
        "group_commentary": commentary,
        "decision": "keep" if keep else original["decision"],
        "decision_reasons": [
            *original["decision_reasons"],
            *(["group_coverage_fallback"] if keep else []),
        ],
        "meta": {
            **original["meta"],
            "quality_assessment": {
                "version": 1,
                "decision": original["decision"],
                "reasons": original["decision_reasons"],
            },
            "selection": {
                "version": 1,
                "decision": "keep" if keep else original["decision"],
                "role": "group_coverage" if keep else "quality_policy",
                "reasons": ["group_coverage_fallback"] if keep else original["decision_reasons"],
            },
        },
    }


@pytest.fixture
def runtime(monkeypatch):
    calls = []
    config = {
        "preview": {"max_size": 256, "jpeg_quality": 85, "prefer_embedded": True},
        "grouping": {"enabled": True},
        "focus_integrity": {"selective_refinement": {}},
        "output_language": "en",
        "commentary_enabled": False,
    }
    frame = SimpleNamespace(focus_gray=SimpleNamespace(size=24 * 24))
    bundle = ScoreBundle(
        scores={"sharpness": 1.0},
        total=1.0,
        boosted=False,
        meta={"focus_preview_size": [24, 24]},
        scene="people",
        scene_raw="refined scene",
        instructions="refined instructions",
        decision="reject",
        decision_reasons=["blur"],
        screening_prior=0.1,
        visible_breakdown={},
        policy_version="refined-policy",
        signals=[{"source": "refined"}],
    )
    decoder = Mock(return_value=frame)
    model = Mock(return_value=bundle)
    commentary = SimpleNamespace(error=None, group_inputs=[])
    state = Mock()
    client, screening = object(), object()

    def decode(*args):
        calls.append("decode")
        return decoder(*args)

    async def compute(*args, **kwargs):
        calls.append("compute")
        return model(*args, **kwargs)

    async def for_group(summary, details):
        calls.append("comment")
        commentary.group_inputs.append((summary, details))
        if commentary.error is not None:
            raise commentary.error
        return GROUP_COMMENT

    async def for_photo(*args, **kwargs):
        return POST_COMMENT

    commentary.for_group = for_group
    commentary.for_photo = for_photo

    def refine(rows, **kwargs):
        calls.append("refine")
        return refine_group(rows, clock=lambda: 0.0, **kwargs)

    select = review_runtime.apply_group_best_candidate_review

    def selection(rows, **kwargs):
        calls.append("select")
        return select(rows, **kwargs)

    boundary = review_runtime.run_coro_sync

    def sync(coro):
        calls.append("async boundary")
        return boundary(coro)

    monkeypatch.setattr(review_runtime, "make_client", lambda _: client)
    monkeypatch.setattr(review_runtime, "make_fast_screening_port", lambda _: screening)
    monkeypatch.setattr(review_runtime, "CommentaryGenerator", lambda **_: commentary)
    monkeypatch.setattr(review_runtime, "decode_raw", decode)
    monkeypatch.setattr(review_runtime, "compute_scores", compute)
    monkeypatch.setattr(review_runtime, "refine_group", refine)
    monkeypatch.setattr(review_runtime, "apply_group_best_candidate_review", selection)
    monkeypatch.setattr(review_runtime, "run_coro_sync", sync)

    def build(*, dry_run=True):
        return review_runtime.build_review_job_executor(
            repository=Mock(), config=config, state=state, progress=Mock(), dry_run=dry_run
        ).review_job

    return SimpleNamespace(
        config=config,
        calls=calls,
        frame=frame,
        bundle=bundle,
        decoder=decoder,
        model=model,
        commentary=commentary,
        state=state,
        client=client,
        screening=screening,
        build=build,
    )


def test_empty_finalization_returns_same_list_without_configuration_or_async_work(runtime):
    job = runtime.build()
    runtime.config["focus_integrity"] = None
    rows = []
    assert job.finalize_group(rows, group_id="g") is rows
    assert runtime.calls == []


@pytest.mark.parametrize("commentary", [False, True])
@pytest.mark.parametrize("coverage", [False, True])
def test_full_payload_order_ties_invalid_quality_and_shallow_aliases(runtime, commentary, coverage):
    runtime.config["commentary_enabled"] = commentary
    runtime.config["grouping"]["best_candidate_review"] = {"enabled": coverage}
    rows = [("z", payload()), ("a", payload())]
    for path, value in [("nan", float("nan")), ("inf", float("inf")), ("missing", None)]:
        item = payload()
        if path == "missing":
            item.pop("score_total")
        else:
            item["score_total"] = value
        rows.append((path, item))
    original = deepcopy(rows)
    result = runtime.build().finalize_group(rows, group_id="g")
    text = GROUP_COMMENT if commentary else ""
    expected = [
        (path, selected(item, keep=coverage and path == "a", commentary=text))
        if path in {"z", "a"}
        else (path, {**item, "group_commentary": text})
        for path, item in rows
    ]
    assert result == expected
    assert rows == original
    for (path, before), (_, after) in zip(rows, result, strict=True):
        assert before is not after
        assert after["scores"] is before["scores"]
        assert after["signals"] is before["signals"]
        assert after["custom"] is before["custom"]
        assert after["previous_group_info"] is before["previous_group_info"]
        assert (after["meta"] is before["meta"]) == (path not in {"z", "a"})
    assert runtime.calls == (
        ["refine", "async boundary", "comment", "select"] if commentary else ["refine", "select"]
    )
    if commentary:
        summary, details = runtime.commentary.group_inputs[0]
        assert summary == [(path, float(item.get("score_total", 0.0))) for path, item in rows]
        assert details == [
            {
                "sharpness": 5.0,
                "_scene": "people",
                "_scene_raw": "baseline scene",
                "_decision": "review",
            }
        ] * len(rows)


@pytest.mark.parametrize("commentary", [False, True])
@pytest.mark.parametrize(
    "case", ["disabled", "gain", "no_gain", "decode_failure", "score_failure", "invalid_score"]
)
def test_refinement_full_payload_and_collaborator_order(runtime, commentary, case):
    runtime.config["commentary_enabled"] = commentary
    runtime.config["focus_integrity"]["selective_refinement"] = {
        "enabled": case != "disabled",
        "max_candidates": 1,
        "focus_max_size": 2048,
    }
    if case == "no_gain":
        runtime.frame.focus_gray.size = 16 * 16
    elif case == "decode_failure":
        runtime.decoder.side_effect = ValueError("decode fixture")
    elif case == "score_failure":
        runtime.model.side_effect = RuntimeError("score fixture")
    elif case == "invalid_score":
        runtime.bundle.total = float("inf")
    before = payload()
    original = deepcopy(before)
    result = runtime.build().finalize_group([("a", before)], group_id="g")
    expected = {**before}
    if case == "gain":
        expected.update(
            score_total=1.0,
            scores={"sharpness": 1.0},
            meta={"focus_preview_size": [24, 24]},
            scene="people",
            scene_raw="refined scene",
            instructions="refined instructions",
            decision="reject",
            decision_reasons=["blur"],
            screening_prior=0.1,
            visible_breakdown={},
            policy_version="refined-policy",
            signals=[{"source": "refined"}],
            skip_write=False,
        )
    if case != "disabled":
        record = {
            "version": 1,
            "triggers": ["unknown_eye_evidence"],
            "attempts": 1,
            "before": {
                "score_total": 5.0,
                "decision": "review",
                "decision_reasons": ["baseline reason"],
                "scores": {"sharpness": 5.0},
                "signals": [{"source": "baseline"}],
                "subject_focus": None,
                "face_eye_evidence": UNKNOWN_EYES,
            },
            "status": "completed"
            if case == "gain"
            else "no_resolution_gain"
            if case == "no_gain"
            else "failed",
            "review_required": True,
            "elapsed_seconds": 0.0,
            "budget_overrun": False,
        }
        if case in {"decode_failure", "score_failure", "invalid_score"}:
            record["error_type"] = "RuntimeError" if case == "score_failure" else "ValueError"
        expected["meta"] = {**expected["meta"], "refinement": record}
    text = GROUP_COMMENT if commentary else ""
    assert result == [("a", selected(expected, keep=True, commentary=text))]
    assert before == original
    assert result[0][1]["custom"] is before["custom"]
    assert result[0][1]["boosted"] is True  # bundle.boosted does not overwrite this key
    expected_calls = ["refine"]
    if case != "disabled":
        expected_calls += ["decode"]
        runtime.decoder.assert_called_once_with(
            "a",
            {"max_size": 256, "jpeg_quality": 85, "prefer_embedded": False, "focus_max_size": 2048},
        )
    if case in {"gain", "score_failure", "invalid_score"}:
        expected_calls += ["async boundary", "compute"]
        runtime.model.assert_called_once_with(
            runtime.frame, runtime.client, runtime.config, fast_screening=runtime.screening
        )
    else:
        runtime.model.assert_not_called()
    if commentary:
        expected_calls += ["async boundary", "comment"]
        assert runtime.commentary.group_inputs == [
            (
                [("a", expected["score_total"])],
                [
                    {
                        **expected["scores"],
                        "_scene": expected["scene"],
                        "_scene_raw": expected["scene_raw"],
                        "_decision": expected["decision"],
                    }
                ],
            )
        ]
    assert runtime.calls == [*expected_calls, "select"]


def test_refinement_and_selection_read_config_at_invocation_commentary_at_construction(runtime):
    job = runtime.build()
    runtime.config["focus_integrity"]["selective_refinement"] = {
        "enabled": True,
        "focus_max_size": 1536,
    }
    runtime.config["grouping"]["best_candidate_review"] = {"enabled": False}
    runtime.config["commentary_enabled"] = True
    result = job.finalize_group([("a", payload())], group_id="g")[0][1]
    assert result["decision"] == "reject"
    assert result["group_commentary"] == ""
    assert runtime.decoder.call_args.args[1]["focus_max_size"] == 1536
    runtime.config["focus_integrity"]["selective_refinement"] = {"enabled": False}
    runtime.config["grouping"]["best_candidate_review"] = {"enabled": True}
    runtime.calls.clear()
    assert job.finalize_group([("a", payload())], group_id="g") == [
        ("a", selected(payload(), keep=True))
    ]
    assert runtime.calls == ["refine", "select"]


def test_collaborators_remain_live_and_selection_config_is_read_after_commentary(
    runtime, monkeypatch
):
    runtime.config["commentary_enabled"] = True
    runtime.config["focus_integrity"]["selective_refinement"] = {"enabled": True}
    job = runtime.build()
    replacement_decoder = Mock(return_value=runtime.frame)

    async def replacement_compute(*args, **kwargs):
        return runtime.bundle

    replacement_model = Mock(side_effect=replacement_compute)
    existing_boundary = review_runtime.run_coro_sync
    replacement_boundary = Mock(side_effect=existing_boundary)

    async def comment_and_change_selection(*args):
        runtime.config["grouping"]["best_candidate_review"] = {"enabled": False}
        return GROUP_COMMENT

    runtime.commentary.for_group = comment_and_change_selection
    monkeypatch.setattr(review_runtime, "decode_raw", replacement_decoder)
    monkeypatch.setattr(review_runtime, "compute_scores", replacement_model)
    monkeypatch.setattr(review_runtime, "run_coro_sync", replacement_boundary)
    result = job.finalize_group([("a", payload())], group_id="g")[0][1]
    assert result["score_total"] == 1.0
    assert result["decision"] == "reject"
    assert result["meta"]["selection"] == {
        "version": 1,
        "decision": "reject",
        "role": "quality_policy",
        "reasons": ["blur"],
    }
    assert result["group_commentary"] == GROUP_COMMENT
    replacement_decoder.assert_called_once()
    replacement_model.assert_called_once_with(
        runtime.frame, runtime.client, runtime.config, fast_screening=runtime.screening
    )
    assert replacement_boundary.call_count == 2
    runtime.decoder.assert_not_called()
    runtime.model.assert_not_called()


@pytest.mark.parametrize("commentary", [False, True])
def test_cached_quality_metadata_is_reused_without_reinterpreting_previous_selection(
    runtime, commentary
):
    runtime.config["commentary_enabled"] = commentary
    before = payload()
    before["decision"] = "keep"
    before["decision_reasons"] = ["old selection reason"]
    quality = {"version": 1, "decision": "reject", "reasons": ["cached blur"]}
    before["meta"].update(quality_assessment=quality, selection={"role": "old selection"})
    original = deepcopy(before)
    text = GROUP_COMMENT if commentary else ""
    expected = selected(
        {**before, "decision": "reject", "decision_reasons": ["cached blur"]},
        keep=True,
        commentary=text,
    )
    result = runtime.build().finalize_group([("a", before)], group_id="g")
    assert result == [("a", expected)]
    assert before == original
    assert result[0][1]["meta"]["quality_assessment"] is quality
    assert result[0][1]["skip_write"] is True
    if commentary:
        assert runtime.commentary.group_inputs[0][1][0]["_decision"] == "keep"


@pytest.mark.parametrize("stage", ["decode", "compute", "comment"])
@pytest.mark.parametrize("error", [KeyboardInterrupt, asyncio.CancelledError])
def test_cancellation_stops_finalization_without_mutating_inputs(runtime, stage, error):
    runtime.config["commentary_enabled"] = True
    runtime.config["focus_integrity"]["selective_refinement"] = {"enabled": stage != "comment"}
    interruption = error()
    if stage == "decode":
        runtime.decoder.side_effect = interruption
    elif stage == "compute":
        runtime.model.side_effect = interruption
    else:
        runtime.commentary.error = interruption
    before = payload()
    original = deepcopy(before)
    with pytest.raises(error) as caught:
        runtime.build().finalize_group([("a", before)], group_id="g")
    assert caught.value is interruption
    assert before == original
    assert "select" not in runtime.calls
    assert ("comment" in runtime.calls) == (stage == "comment")


def test_commentary_error_and_invalid_commentary_score_propagate_before_selection(runtime):
    runtime.config["commentary_enabled"] = True
    job = runtime.build()
    before = payload()
    runtime.commentary.error = ValueError("comment fixture")
    with pytest.raises(ValueError, match="comment fixture"):
        job.finalize_group([("a", before)], group_id="g")
    assert runtime.calls == ["refine", "async boundary", "comment"]
    assert before == payload()
    runtime.calls.clear()
    before["score_total"] = None
    with pytest.raises(TypeError):
        job.finalize_group([("a", before)], group_id="g")
    assert runtime.calls == ["refine"]


@pytest.mark.parametrize("commentary", [False, True])
@pytest.mark.parametrize("refinement", [False, True])
@pytest.mark.parametrize("imported_rating", ["0", "5"])
def test_finalized_writer_output_and_complete_projection(
    runtime, monkeypatch, commentary, refinement, imported_rating
):
    runtime.config["commentary_enabled"] = commentary
    runtime.config["focus_integrity"]["selective_refinement"] = {"enabled": refinement}
    tree = ET.fromstring(
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<rdf:Description xmp:Rating="{imported_rating}"><dc:subject><rdf:Bag>'
        "<rdf:li>family</rdf:li><rdf:li>material-agent:reject</rdf:li>"
        "</rdf:Bag></dc:subject></rdf:Description></rdf:RDF>"
    )
    writer = xmp.ExifToolXMPWriter()
    monkeypatch.setattr(writer, "_sidecar_path", lambda _: Path("virtual.xmp"))
    monkeypatch.setattr(
        writer,
        "preview_projection",
        lambda _path, **kwargs: xmp._projection_receipt(
            tree,
            kwargs["rating"],
            kwargs["subject_tags"],
            kwargs["instructions"],
            kwargs["description"],
        ),
    )
    monkeypatch.setattr(review_runtime, "ExifToolXMPWriter", lambda _: writer)
    job = runtime.build()
    finalized = job.finalize_group([("a", payload())], group_id="g")[0][1]
    before_write = deepcopy(finalized)
    job.write_file("a", finalized, rank=2, group_id="g", group_size=3)
    score = 1.0 if refinement else 5.0
    rating = 1 if refinement else 3
    description = "Group ranking: this photo ranks #2 out of 3 photos in the group."
    if commentary:
        description += f"\n\n{GROUP_COMMENT}\n\n{POST_COMMENT}"
    instructions = f"Sharpness:{score:.1f}"
    output = {
        "rating": rating,
        "subject_tags": [
            f"pj:score={score:.1f}",
            "pj:rank=2/3",
            "pj:group=g",
            "pj:decision=keep",
            "pj:boosted",
            "pj:scene=People",
        ],
        "instructions": instructions,
        "description": description,
        "group_id": "g",
        "group_rank": 2,
        "group_size": 3,
    }
    proposed = {
        "rating": rating,
        "keywords": ["family", "material-agent:keep"],
        "instructions": instructions,
        "description": description,
    }
    imported = {
        "rating": imported_rating,
        "keywords": ["family", "material-agent:reject"],
        "instructions": None,
        "description": None,
    }
    fields = {
        key: {
            "imported": imported[key],
            "requested": value,
            "effective": imported[key],
            "planned": imported_rating if key == "rating" and imported_rating == "5" else value,
            "status": "skipped" if key == "rating" and imported_rating == "5" else "planned",
            "reason": "preserved_nonzero"
            if key == "rating" and imported_rating == "5"
            else "ai_projection",
            "conflict": key == "rating" and imported_rating == "5",
            "imported_author": "unknown",
        }
        for key, value in proposed.items()
    }
    receipt = {
        "version": 1,
        "status": "planned",
        "fields": fields,
        "rating": "preserved_nonzero" if imported_rating == "5" else "planned",
        "requested_rating": rating,
        "effective_rating": imported_rating,
        "keywords": "planned",
        "source": "existing_sidecar",
    }
    assert finalized == {**before_write, "output_preview": output, "xmp_projection": receipt}
    runtime.state.mark_done.assert_not_called()
    runtime.state.record_xmp_projection.assert_not_called()
