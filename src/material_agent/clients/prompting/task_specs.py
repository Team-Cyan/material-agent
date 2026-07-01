from __future__ import annotations

from ..prompts import (
    build_fast_prompt,
    build_fast_response_format,
    build_full_prompt,
    build_full_response_format,
    build_group_commentary_prompt,
    build_group_commentary_response_format,
    build_post_commentary_prompt,
    build_post_commentary_response_format,
)
from .evaluation import (
    FAST_SCORE_EVALUATION,
    FULL_SCORE_EVALUATION,
    GROUP_COMMENTARY_EVALUATION,
    POST_COMMENTARY_EVALUATION,
)
from .types import PromptTaskSpec


def _fast_prompt_factory(
    *,
    output_language: str,
    prompt_preset: str,
    extra_instructions: str | None,
    structured_output: bool,
    **_: object,
) -> str:
    return build_fast_prompt(
        structured_output=structured_output,
        prompt_preset=prompt_preset,
    )


def _full_prompt_factory(
    *,
    output_language: str,
    prompt_preset: str,
    extra_instructions: str | None,
    structured_output: bool,
    **_: object,
) -> str:
    return build_full_prompt(
        structured_output=structured_output,
        output_language=output_language,
        prompt_preset=prompt_preset,
        extra_instructions=extra_instructions,
    )


def _group_commentary_prompt_factory(
    *,
    output_language: str,
    prompt_preset: str,
    extra_instructions: str | None,
    structured_output: bool,
    group_data: str,
) -> str:
    return build_group_commentary_prompt(
        group_data,
        output_language=output_language,
        prompt_preset=prompt_preset,
        extra_instructions=extra_instructions,
    )


def _post_commentary_prompt_factory(
    *,
    output_language: str,
    prompt_preset: str,
    extra_instructions: str | None,
    structured_output: bool,
    score_line: str,
    group_commentary: str = "",
) -> str:
    return build_post_commentary_prompt(
        score_line,
        group_commentary,
        output_language=output_language,
        prompt_preset=prompt_preset,
        extra_instructions=extra_instructions,
    )


PROMPT_TASK_SPECS: dict[str, PromptTaskSpec] = {
    "fast_score": PromptTaskSpec(
        name="fast_score",
        model_config_key="fast_vision_model",
        schema_request_key="fast_vision_schema",
        default_schema_name="material_agent.fast_screening_signals",
        temperature_key="vision_temperature",
        max_tokens_key="fast_vision_max_tokens",
        prompt_extra_key=None,
        prompt_factory=_fast_prompt_factory,
        response_format_factory=build_fast_response_format,
        evaluation_policy=FAST_SCORE_EVALUATION,
    ),
    "full_score": PromptTaskSpec(
        name="full_score",
        model_config_key="full_vision_model",
        schema_request_key="vision_schema",
        default_schema_name="material_agent.full_score",
        temperature_key="vision_temperature",
        max_tokens_key="vision_max_tokens",
        prompt_extra_key="full_prompt_extra",
        prompt_factory=_full_prompt_factory,
        response_format_factory=build_full_response_format,
        evaluation_policy=FULL_SCORE_EVALUATION,
    ),
    "group_commentary": PromptTaskSpec(
        name="group_commentary",
        model_config_key="commentary_model",
        schema_request_key="group_commentary_schema",
        default_schema_name="material_agent.group_commentary",
        temperature_key="commentary_temperature",
        max_tokens_key="group_commentary_max_tokens",
        prompt_extra_key="group_prompt_extra",
        prompt_factory=_group_commentary_prompt_factory,
        response_format_factory=build_group_commentary_response_format,
        evaluation_policy=GROUP_COMMENTARY_EVALUATION,
    ),
    "post_commentary": PromptTaskSpec(
        name="post_commentary",
        model_config_key="commentary_model",
        schema_request_key="post_commentary_schema",
        default_schema_name="material_agent.post_commentary",
        temperature_key="commentary_temperature",
        max_tokens_key="post_commentary_max_tokens",
        prompt_extra_key="post_prompt_extra",
        prompt_factory=_post_commentary_prompt_factory,
        response_format_factory=build_post_commentary_response_format,
        evaluation_policy=POST_COMMENTARY_EVALUATION,
    ),
}

SCORING_TASK_SPECS = PROMPT_TASK_SPECS
