from .types import EvaluationPolicy

FULL_SCORE_EVALUATION = EvaluationPolicy(
    name="scoring.full.phase1",
    runtime_checks=("structured_output_success", "schema_validity"),
    benchmark_metrics=(
        "score_range",
        "favorite_value_ratio",
        "repeated_score_vector_ratio",
        "avg_group_score_range",
    ),
)

FAST_SCORE_EVALUATION = EvaluationPolicy(
    name="scoring.fast.phase1",
    runtime_checks=("structured_output_success", "schema_validity"),
    benchmark_metrics=("signal_contract_valid",),
)

GROUP_COMMENTARY_EVALUATION = EvaluationPolicy(
    name="commentary.group.phase2",
    runtime_checks=("structured_output_success", "schema_validity"),
    benchmark_metrics=("commentary_specificity", "commentary_repetition"),
)

POST_COMMENTARY_EVALUATION = EvaluationPolicy(
    name="commentary.post.phase2",
    runtime_checks=("structured_output_success", "schema_validity"),
    benchmark_metrics=("post_commentary_specificity", "post_commentary_repetition"),
)
