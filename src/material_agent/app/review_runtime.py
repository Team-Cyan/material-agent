from ..adapters.metadata.exiftool_xmp import ExifToolXMPWriter
from ..adapters.progress import RichEventSink
from ..app.job_executor import JobExecutor
from ..app.jobs import ReviewPhotosJob
from ..app.local_embedding_identity import build_local_embedding_cache_key
from ..clients.base import make_client, make_fast_screening_port
from ..domain.commentary import (
    CommentaryGenerator,
    build_photo_commentary_context,
    rank_description,
    split_group_commentary_sections,
)
from ..domain.grouper import Grouper
from ..domain.layered_decision import apply_group_review_fallback
from ..domain.scoring_engine import (
    build_score_instructions,
    build_visible_breakdown_instructions,
    build_xmp_instructions,
    compute_scores,
    decode_raw,
)
from ..utils.async_tools import run_coro_sync
from ..utils.constants import scene_label


def build_review_job_executor(
    *,
    repository,
    config: dict,
    state,
    progress,
    dry_run: bool,
) -> JobExecutor:
    output_language = config.get("output_language", "zh")
    client = make_client(config)
    fast_screening = make_fast_screening_port(config)
    commentary = CommentaryGenerator(
        client=client,
        enabled=config.get("commentary_enabled", False),
        output_language=output_language,
    )
    writer = ExifToolXMPWriter(config.get("xmp", {}))
    event_sink = RichEventSink(progress)

    def embedding_for_file(file_path: str) -> list[float] | None:
        embedding_cfg = config.get("grouping", {}).get("embedding_similarity", {})
        if not embedding_cfg.get("enabled", False) or not hasattr(client, "embed_image"):
            return None
        frame = decode_raw(file_path, config["preview"])
        result = run_coro_sync(client.embed_image(frame.jpeg_bytes))
        return result.get("vector")

    def group_files(file_paths: list[str]) -> list[list[str]]:
        if not file_paths:
            return []
        if config["grouping"]["enabled"]:
            embedding_enabled = bool(
                config["grouping"].get("embedding_similarity", {}).get("enabled", False)
            )
            model_key = (
                build_local_embedding_cache_key(config) if embedding_enabled else ""
            )
            return Grouper(
                config["grouping"],
                embedding_loader=embedding_for_file,
                embedding_model_key=model_key,
            ).group(file_paths, state=state, progress=progress)
        return [[file_path] for file_path in file_paths]

    def prepare_score(file_path: str) -> dict:
        cached = state.get_cached_score_payload(file_path) if state is not None else None
        if cached:
            return {
                "file_path": file_path,
                "cached": True,
                "score_total": cached["total"],
                "scores": cached["scores"],
                "meta": cached["meta"],
                "scene": cached.get("scene", "other"),
                "scene_raw": cached.get("scene_raw", ""),
                "instructions": build_score_instructions(cached["scores"]),
                "boosted": bool(cached.get("boosted", False)),
                "decision": cached.get("decision"),
                "decision_reasons": cached.get("decision_reasons", []),
                "screening_prior": cached.get("screening_prior"),
                "visible_breakdown": cached.get("visible_breakdown", {}),
                "policy_version": cached.get("policy_version", "layered-v1"),
                "signals": cached.get("signals", []),
                "previous_group_info": cached.get("group_info"),
                "skip_write": cached.get("status") == "done",
            }
        frame = decode_raw(file_path, config["preview"])
        return {
            "file_path": file_path,
            "cached": False,
            "frame": frame,
        }

    def score_prepared(prepared: dict) -> dict:
        if prepared.get("cached"):
            return {key: value for key, value in prepared.items() if key not in {"file_path", "cached"}}
        file_path = prepared["file_path"]
        frame = prepared["frame"]
        bundle = run_coro_sync(compute_scores(frame, client, config, fast_screening=fast_screening))
        if state is not None and not dry_run:
            state.mark_scored(
                file_path,
                bundle.total,
                bundle.scores,
                bundle.meta,
                scene=bundle.scene,
                scene_raw=bundle.scene_raw,
                decision=bundle.decision,
                decision_reasons=bundle.decision_reasons,
                screening_prior=bundle.screening_prior,
                visible_breakdown=bundle.visible_breakdown,
                policy_version=bundle.policy_version,
                signals=bundle.signals,
            )
        return {
            "score_total": bundle.total,
            "scores": bundle.scores,
            "meta": bundle.meta,
            "scene": bundle.scene,
            "scene_raw": bundle.scene_raw,
            "instructions": bundle.instructions,
            "boosted": False,
            "decision": bundle.decision,
            "decision_reasons": bundle.decision_reasons,
            "screening_prior": bundle.screening_prior,
            "visible_breakdown": bundle.visible_breakdown,
            "policy_version": bundle.policy_version,
            "signals": bundle.signals,
        }

    def finalize_group(group_results: list[tuple[str, dict]], *, group_id: str) -> list[tuple[str, dict]]:
        if not group_results:
            return group_results

        group_commentary = run_coro_sync(
            commentary.for_group(
                [(file_path, float(payload.get("score_total", 0.0))) for file_path, payload in group_results],
                [
                    {
                        **payload.get("scores", {}),
                        "_scene": payload.get("scene", "other"),
                        "_scene_raw": payload.get("scene_raw", ""),
                        "_decision": payload.get("decision"),
                    }
                    for _, payload in group_results
                ],
            )
        )
        results_with_commentary = [
            (
                file_path,
                {
                    **payload,
                    "group_commentary": group_commentary,
                },
            )
            for file_path, payload in group_results
        ]
        return apply_group_review_fallback(
            results_with_commentary,
            enabled=config.get("screening_policy", {}).get("top1_review_fallback", True),
        )

    def write_file(file_path: str, score_payload: dict, *, rank: int, group_id: str, group_size: int) -> None:
        total_score = float(score_payload.get("score_total", 0.0))
        scores = score_payload.get("scores", {})
        meta = score_payload.get("meta", {})
        scene = score_payload.get("scene", "other")
        scene_raw = score_payload.get("scene_raw", "")
        instructions = score_payload.get("instructions") or build_score_instructions(scores)
        group_commentary = score_payload.get("group_commentary", "")
        boosted = bool(score_payload.get("boosted", False))
        decision = score_payload.get("decision")
        decision_reasons = list(score_payload.get("decision_reasons", []))
        visible_breakdown = score_payload.get("visible_breakdown", {})
        star = writer.score_to_stars(total_score)

        if dry_run:
            print(
                f"[dry-run] {file_path}: rating={star}, score={total_score:.1f}, "
                f"scene={scene}, rank={rank}/{group_size}"
            )
            return

        commentary_context = build_photo_commentary_context(
            instructions,
            scores=scores,
            scene=scene,
            scene_raw=scene_raw,
            decision=decision,
            visible_breakdown=visible_breakdown,
            output_language=output_language,
        )
        post_commentary = run_coro_sync(
            commentary.for_photo(
                commentary_context,
                group_commentary,
                scores,
                scene=scene,
                scene_raw=scene_raw,
                decision=decision,
                rank=rank,
                group_size=group_size,
                variant_key=file_path,
                visible_breakdown=visible_breakdown,
            )
        )
        description = (
            f"{rank_description(rank, group_size, output_language)}\n\n"
            f"{group_commentary}\n\n{post_commentary}"
        ).strip()
        xmp_instructions = (
            build_visible_breakdown_instructions(visible_breakdown, output_language=output_language)
            if visible_breakdown
            else build_xmp_instructions(scores, output_language=output_language)
        )
        subject_tags = writer.build_subject_tags(
            score=total_score,
            rank=rank,
            group_size=group_size,
            group_id=group_id,
            boosted=boosted,
            decision=decision,
        )
        subject_tags.append(f"pj:scene={scene_label(scene, output_language)}")

        writer.write(
            file_path,
            rating=star,
            subject_tags=subject_tags,
            instructions=xmp_instructions,
            description=description,
        )

        if state is not None:
            commentary_issues, commentary_shooting = split_group_commentary_sections(
                group_commentary,
                output_language=output_language,
            )
            state.mark_done(
                file_path,
                total_score=total_score,
                star_rating=star,
                group_boosted=boosted,
                scores=scores,
                metadata=meta,
                group_info={"group_id": group_id, "group_rank": rank, "group_size": group_size},
                scene=scene,
                scene_raw=scene_raw,
                decision=decision,
                decision_reasons=decision_reasons,
                screening_prior=score_payload.get("screening_prior"),
                visible_breakdown=visible_breakdown,
                policy_version=score_payload.get("policy_version", "layered-v1"),
                signals=score_payload.get("signals", []),
                commentary_group_issues=commentary_issues,
                commentary_shooting=commentary_shooting,
                commentary_post=post_commentary,
                xmp_payload={
                    "rating": star,
                    "instructions": xmp_instructions,
                    "description": description,
                },
            )

    review_job = ReviewPhotosJob(
        repository=repository,
        event_sink=event_sink,
        group_files=group_files,
        prepare_score=prepare_score,
        score_prepared=score_prepared,
        finalize_group=finalize_group,
        write_file=write_file,
        score_prefetch_window=config.get("review_pipeline", {}).get("score_prefetch_window", 1),
        write_outputs=not dry_run,
    )
    return JobExecutor(review_job)
