from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

PromptFactory = Callable[..., str]
ResponseFormatFactory = Callable[..., dict]


@dataclass(frozen=True)
class EvaluationPolicy:
    name: str
    runtime_checks: tuple[str, ...] = ()
    benchmark_metrics: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptTaskSpec:
    name: str
    model_config_key: str
    schema_request_key: str
    default_schema_name: str
    temperature_key: str
    max_tokens_key: str
    prompt_extra_key: str | None
    prompt_factory: PromptFactory
    response_format_factory: ResponseFormatFactory
    evaluation_policy: EvaluationPolicy


@dataclass(frozen=True)
class PromptProfile:
    request_overrides: dict[str, Any] = field(default_factory=dict)
    prompt_overrides: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptBundle:
    task: str
    model: str
    prompt: str
    response_format: dict | None
    request_options: dict[str, Any]
    evaluation_policy: EvaluationPolicy
