from __future__ import annotations

import asyncio
import copy
from dataclasses import asdict, dataclass
from datetime import datetime
import json
from itertools import product
from pathlib import Path
import re
import time
from typing import Any

import cv2

from ..clients.omlx import AsyncOMLXClient
from ..clients.prompts import (
    build_fast_prompt,
    build_full_prompt,
    build_post_commentary_prompt,
    build_post_commentary_response_format,
)
from ..clients.protocol import extract_last_json_object
from ..adapters.models.omlx.contracts import (
    validate_omlx_fast_score_payload,
    validate_omlx_full_score_payload,
)
from .omlx_instance_service import OMLXInstanceService
from ..utils.config_validator import sync_omlx_model_selection

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_DEFAULT_SCORE_LINE = (
    "exp:9.4 sharp:3.9 subj:8.5 comp:7.5 lit:7.0 color:6.0 clar:7.0 dep:7.5 mood:8.5"
)
_DEFAULT_GROUP_COMMENTARY = "【组内问题】整体偏暗。\n【拍摄建议】拍摄时补一点面光。"
_ACTIONABLE_TOKENS = (
    "提",
    "压",
    "降",
    "减",
    "加",
    "裁",
    "校正",
    "拉",
    "控",
    "补",
    "锐化",
    "降噪",
    "白平衡",
    "色温",
    "饱和度",
    "对比",
    "阴影",
    "高光",
    "曝光",
    "反差",
)
_SPECIFIC_TOKENS = (
    "阴影",
    "高光",
    "白平衡",
    "色温",
    "曝光",
    "饱和度",
    "对比",
    "锐化",
    "降噪",
    "裁切",
    "局部",
    "背景",
    "肤色",
    "偏色",
)
_PLACEHOLDER_TOKENS = {"string", "text", "todo", "tbd", "n/a", "na"}


@dataclass(slots=True)
class BenchmarkCandidate:
    contract_mode: str
    prompt_preset: str
    vision_temperature: float
    commentary_temperature: float
    vision_max_tokens: int
    post_commentary_max_tokens: int
    enable_thinking: bool
    image_max_edge: int
    vision_jpeg_quality: int

    @property
    def slug(self) -> str:
        thinking = "thinking-on" if self.enable_thinking else "thinking-off"
        return (
            f"{self.contract_mode}__{self.prompt_preset}__"
            f"vt{self.vision_temperature:g}__ct{self.commentary_temperature:g}__"
            f"vm{self.vision_max_tokens}__pm{self.post_commentary_max_tokens}__"
            f"ie{self.image_max_edge}__jq{self.vision_jpeg_quality}__{thinking}"
        )


class OMLXBenchmarkService:
    def __init__(self, *, client_cls=AsyncOMLXClient):
        self.client_cls = client_cls

    def run(
        self,
        config: dict,
        *,
        models: list[str],
        mode: str,
        repeat_count: int,
        sample_set: list[str] | None = None,
        result_path: str | None = None,
        contract_modes: list[str] | None = None,
        prompt_presets: list[str] | None = None,
        vision_temperatures: list[float] | None = None,
        commentary_temperatures: list[float] | None = None,
        vision_max_tokens: list[int] | None = None,
        post_commentary_max_tokens: list[int] | None = None,
        enable_thinking_options: list[bool] | None = None,
        image_max_edges: list[int] | None = None,
        vision_jpeg_qualities: list[int] | None = None,
    ) -> dict[str, Any]:
        normalized_mode = str(mode).strip().lower()
        if normalized_mode not in {"single_fixture", "kv_cache_batch"}:
            raise ValueError(f"Unsupported benchmark mode: {mode!r}")
        if repeat_count < 1:
            raise ValueError("repeat_count must be >= 1")

        sample_paths = self._resolve_sample_paths(normalized_mode, sample_set)
        run_root = self._resolve_result_root(result_path)
        run_dir = run_root / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True, exist_ok=True)
        attempts_path = run_dir / "attempts.jsonl"

        preflight_status = self._benchmark_status(config)
        if not preflight_status.get("reachable"):
            raise RuntimeError(
                f"OMLX benchmark runtime is unreachable at {preflight_status.get('base_url')}: "
                f"{preflight_status.get('error') or 'unknown error'}"
            )

        candidate_list = self._build_candidates(
            config,
            contract_modes=contract_modes,
            prompt_presets=prompt_presets,
            vision_temperatures=vision_temperatures,
            commentary_temperatures=commentary_temperatures,
            vision_max_tokens=vision_max_tokens,
            post_commentary_max_tokens=post_commentary_max_tokens,
            enable_thinking_options=enable_thinking_options,
            image_max_edges=image_max_edges,
            vision_jpeg_qualities=vision_jpeg_qualities,
        )

        results: list[dict[str, Any]] = []
        with attempts_path.open("w", encoding="utf-8") as attempts_handle:
            for model in models:
                for candidate in candidate_list:
                    candidate_config = self._build_candidate_config(config, model, candidate)
                    if normalized_mode == "single_fixture":
                        summary = asyncio.run(
                            self._run_single_fixture(
                                model=model,
                                config=candidate_config,
                                candidate=candidate,
                                sample_path=sample_paths[0],
                                repeat_count=repeat_count,
                                attempts_handle=attempts_handle,
                            )
                        )
                    else:
                        summary = asyncio.run(
                            self._run_kv_cache_batch(
                                model=model,
                                config=candidate_config,
                                candidate=candidate,
                                sample_paths=sample_paths,
                                attempts_handle=attempts_handle,
                            )
                        )
                    summary["contract_execution"] = self._describe_contract_execution(
                        candidate,
                        preflight_status,
                    )
                    results.append(summary)

        summary = {
            "run_dir": str(run_dir),
            "attempts_path": str(attempts_path),
            "result_root": str(run_root),
            "mode": normalized_mode,
            "repeat_count": repeat_count,
            "sample_paths": [str(path) for path in sample_paths],
            "cache_enabled": bool(config.get("omlx", {}).get("cache_enabled", True)),
            "preflight_status": preflight_status,
            "runtime_contract_support": self._build_runtime_contract_support(preflight_status),
            "results": results,
            "best_by_model": self._collect_best_by_model(results, normalized_mode),
        }

        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        best_path = run_root / "best_candidates.json"
        self._update_best_candidates(best_path, summary["best_by_model"], normalized_mode)
        return summary

    def _build_candidates(
        self,
        config: dict,
        *,
        contract_modes: list[str] | None,
        prompt_presets: list[str] | None,
        vision_temperatures: list[float] | None,
        commentary_temperatures: list[float] | None,
        vision_max_tokens: list[int] | None,
        post_commentary_max_tokens: list[int] | None,
        enable_thinking_options: list[bool] | None,
        image_max_edges: list[int] | None,
        vision_jpeg_qualities: list[int] | None,
    ) -> list[BenchmarkCandidate]:
        omlx = config.get("omlx", {})
        requests = omlx.get("requests", {})
        candidates = product(
            contract_modes or [str(requests.get("contract_mode", "structured_outputs")).lower()],
            prompt_presets or [str(requests.get("prompt_preset", "default")).lower()],
            vision_temperatures or [float(omlx.get("vision_temperature", 0.0))],
            commentary_temperatures or [float(omlx.get("commentary_temperature", 0.0))],
            vision_max_tokens or [int(omlx.get("vision_max_tokens", 192))],
            post_commentary_max_tokens or [int(omlx.get("post_commentary_max_tokens", 160))],
            enable_thinking_options or [bool(requests.get("enable_thinking", False))],
            image_max_edges or [int(omlx.get("vision_image_max_edge", 1024))],
            vision_jpeg_qualities or [int(omlx.get("vision_jpeg_quality", 92))],
        )
        return [
            BenchmarkCandidate(
                contract_mode=str(contract_mode).lower(),
                prompt_preset=str(prompt_preset).lower(),
                vision_temperature=float(vision_temperature),
                commentary_temperature=float(commentary_temperature),
                vision_max_tokens=int(candidate_vision_max_tokens),
                post_commentary_max_tokens=int(candidate_post_max_tokens),
                enable_thinking=bool(enable_thinking),
                image_max_edge=int(candidate_image_max_edge),
                vision_jpeg_quality=int(candidate_jpeg_quality),
            )
            for (
                contract_mode,
                prompt_preset,
                vision_temperature,
                commentary_temperature,
                candidate_vision_max_tokens,
                candidate_post_max_tokens,
                enable_thinking,
                candidate_image_max_edge,
                candidate_jpeg_quality,
            ) in candidates
        ]

    def _build_candidate_config(
        self, config: dict, model: str, candidate: BenchmarkCandidate
    ) -> dict:
        candidate_config = copy.deepcopy(config)
        sync_omlx_model_selection(
            candidate_config,
            full_vision_model=model,
            commentary_model=model,
            fast_vision_model=model,
        )
        omlx = candidate_config.setdefault("omlx", {})
        requests = omlx.setdefault("requests", {})
        omlx["vision_temperature"] = candidate.vision_temperature
        omlx["commentary_temperature"] = candidate.commentary_temperature
        omlx["vision_max_tokens"] = candidate.vision_max_tokens
        omlx["post_commentary_max_tokens"] = candidate.post_commentary_max_tokens
        omlx["vision_image_max_edge"] = candidate.image_max_edge
        omlx["vision_jpeg_quality"] = candidate.vision_jpeg_quality
        omlx["output_language"] = candidate_config.get("output_language", "zh")
        omlx["log_level"] = candidate_config.get("log_level", "info")
        requests["contract_mode"] = candidate.contract_mode
        requests["prompt_preset"] = candidate.prompt_preset
        requests["model_profile_mode"] = "off"
        requests["enable_thinking"] = candidate.enable_thinking
        return omlx

    async def _run_single_fixture(
        self,
        *,
        model: str,
        config: dict,
        candidate: BenchmarkCandidate,
        sample_path: Path,
        repeat_count: int,
        attempts_handle,
    ) -> dict[str, Any]:
        client = self.client_cls(config)
        jpeg_bytes = self._load_image_bytes(
            sample_path,
            max_edge=int(config.get("vision_image_max_edge", 1024)),
            jpeg_quality=int(config.get("vision_jpeg_quality", 92)),
        )
        attempts: list[dict[str, Any]] = []
        for iteration in range(1, repeat_count + 1):
            attempts.extend(
                [
                    await self._run_fast_attempt(
                        client, model, candidate, sample_path, jpeg_bytes, iteration
                    ),
                    await self._run_full_attempt(
                        client, model, candidate, sample_path, jpeg_bytes, iteration
                    ),
                    await self._run_post_attempt(client, model, candidate, iteration),
                ]
            )
            for attempt in attempts[-3:]:
                attempts_handle.write(json.dumps(attempt, ensure_ascii=False) + "\n")

        task_summaries = {
            task: self._summarize_attempts(
                [attempt for attempt in attempts if attempt["task"] == task]
            )
            for task in ("fast", "full", "post")
        }
        overall_schema_success_rate = sum(
            summary["schema_success_rate"] for summary in task_summaries.values()
        ) / len(task_summaries)
        overall_json_success_rate = sum(
            summary["json_success_rate"] for summary in task_summaries.values()
        ) / len(task_summaries)
        overall_average_latency_ms = sum(
            summary["average_latency_ms"] for summary in task_summaries.values()
        ) / len(task_summaries)

        return {
            "model": model,
            "mode": "single_fixture",
            "candidate": asdict(candidate),
            "sample_path": str(sample_path),
            "task_summaries": task_summaries,
            "overall_json_success_rate": round(overall_json_success_rate, 4),
            "overall_schema_success_rate": round(overall_schema_success_rate, 4),
            "overall_average_latency_ms": round(overall_average_latency_ms, 2),
            "post_quality_average": task_summaries["post"]["quality_average"],
            "best_rank_key": [
                round(overall_schema_success_rate, 6),
                -round(task_summaries["full"]["average_latency_ms"], 6),
                round(task_summaries["post"]["quality_average"], 6),
            ],
        }

    async def _run_kv_cache_batch(
        self,
        *,
        model: str,
        config: dict,
        candidate: BenchmarkCandidate,
        sample_paths: list[Path],
        attempts_handle,
    ) -> dict[str, Any]:
        client = self.client_cls(config)
        attempts: list[dict[str, Any]] = []
        for index, sample_path in enumerate(sample_paths, start=1):
            jpeg_bytes = self._load_image_bytes(
                sample_path,
                max_edge=int(config.get("vision_image_max_edge", 1024)),
                jpeg_quality=int(config.get("vision_jpeg_quality", 92)),
            )
            attempt = await self._run_full_attempt(
                client,
                model,
                candidate,
                sample_path,
                jpeg_bytes,
                iteration=index,
                task="kv_full",
            )
            attempts.append(attempt)
            attempts_handle.write(json.dumps(attempt, ensure_ascii=False) + "\n")

        first_latency_ms = attempts[0]["latency_ms"] if attempts else 0.0
        subsequent = attempts[1:]
        subsequent_average_ms = (
            round(sum(attempt["latency_ms"] for attempt in subsequent) / len(subsequent), 2)
            if subsequent
            else first_latency_ms
        )
        summary = self._summarize_attempts(attempts)
        summary["first_latency_ms"] = round(first_latency_ms, 2)
        summary["subsequent_average_latency_ms"] = subsequent_average_ms
        summary["cache_speedup_ms"] = round(first_latency_ms - subsequent_average_ms, 2)
        return {
            "model": model,
            "mode": "kv_cache_batch",
            "candidate": asdict(candidate),
            "sample_count": len(sample_paths),
            "sample_paths": [str(path) for path in sample_paths],
            "task_summaries": {"kv_full": summary},
            "overall_json_success_rate": summary["json_success_rate"],
            "overall_schema_success_rate": summary["schema_success_rate"],
            "overall_average_latency_ms": summary["average_latency_ms"],
            "best_rank_key": [
                round(summary["schema_success_rate"], 6),
                -round(summary["average_latency_ms"], 6),
                -round(summary["subsequent_average_latency_ms"], 6),
            ],
        }

    async def _run_fast_attempt(
        self,
        client: AsyncOMLXClient,
        model: str,
        candidate: BenchmarkCandidate,
        sample_path: Path,
        jpeg_bytes: bytes,
        iteration: int,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        raw_text = ""
        json_success = False
        schema_success = False
        error = ""
        try:
            raw_text = await client._vision_raw(
                client.fast_vision_model,
                build_fast_prompt(
                    structured_output=True,
                    prompt_preset=client.prompt_preset,
                ),
                jpeg_bytes,
                enable_thinking=client.structured_enable_thinking,
                max_tokens=client.fast_vision_max_tokens,
                response_mode="fast",
            )
        except Exception as exc:  # pragma: no cover - exercised in benchmark smoke path
            error = str(exc)
        latency_ms = (time.perf_counter() - started) * 1000
        if raw_text:
            try:
                data = extract_last_json_object(raw_text)
                json_success = True
                validate_omlx_fast_score_payload(data)
                schema_success = True
            except Exception as exc:  # pragma: no cover - exercised in benchmark smoke path
                error = str(exc)
        return self._build_attempt_record(
            task="fast",
            model=model,
            candidate=candidate,
            sample_path=sample_path,
            iteration=iteration,
            latency_ms=latency_ms,
            raw_text=raw_text,
            json_success=json_success,
            schema_success=schema_success,
            error=error,
        )

    async def _run_full_attempt(
        self,
        client: AsyncOMLXClient,
        model: str,
        candidate: BenchmarkCandidate,
        sample_path: Path,
        jpeg_bytes: bytes,
        iteration: int,
        *,
        task: str = "full",
    ) -> dict[str, Any]:
        started = time.perf_counter()
        raw_text = ""
        json_success = False
        schema_success = False
        error = ""
        try:
            raw_text = await client._vision_raw(
                client.full_vision_model,
                build_full_prompt(
                    structured_output=True,
                    output_language=client.output_language,
                    prompt_preset=client.prompt_preset,
                ),
                jpeg_bytes,
                enable_thinking=client.structured_enable_thinking,
                max_tokens=client.vision_max_tokens,
                response_mode="full",
            )
        except Exception as exc:  # pragma: no cover - exercised in benchmark smoke path
            error = str(exc)
        latency_ms = (time.perf_counter() - started) * 1000
        if raw_text:
            try:
                data = extract_last_json_object(raw_text)
                json_success = True
                validate_omlx_full_score_payload(data)
                schema_success = True
            except Exception as exc:  # pragma: no cover - exercised in benchmark smoke path
                error = str(exc)
        return self._build_attempt_record(
            task=task,
            model=model,
            candidate=candidate,
            sample_path=sample_path,
            iteration=iteration,
            latency_ms=latency_ms,
            raw_text=raw_text,
            json_success=json_success,
            schema_success=schema_success,
            error=error,
        )

    async def _run_post_attempt(
        self,
        client: AsyncOMLXClient,
        model: str,
        candidate: BenchmarkCandidate,
        iteration: int,
    ) -> dict[str, Any]:
        prompt = build_post_commentary_prompt(
            _DEFAULT_SCORE_LINE,
            _DEFAULT_GROUP_COMMENTARY,
            output_language=client.output_language,
            prompt_preset=client.prompt_preset,
        )
        response_format = build_post_commentary_response_format(
            client.post_commentary_schema_name,
            contract_mode=client.contract_mode,
        )
        started = time.perf_counter()
        raw_text = ""
        json_success = False
        schema_success = False
        error = ""
        quality = {
            "format_valid": 0.0,
            "actionable": 0.0,
            "specificity": 0.0,
            "photo_relevance": 0.0,
            "language_quality": 0.0,
            "average": 0.0,
        }
        try:
            raw_text = await client.generate_text(
                prompt,
                client.commentary_model,
                response_format=response_format,
                max_tokens=client.post_commentary_max_tokens,
                temperature=client.commentary_temperature,
            )
        except Exception as exc:  # pragma: no cover - exercised in benchmark smoke path
            error = str(exc)
        latency_ms = (time.perf_counter() - started) * 1000
        if raw_text:
            try:
                data = extract_last_json_object(raw_text)
                json_success = True
                if (
                    set(data) != {"post"}
                    or not isinstance(data.get("post"), str)
                    or not data["post"].strip()
                ):
                    raise ValueError(
                        "post commentary payload must contain one non-empty 'post' string"
                    )
                schema_success = True
                quality = self._score_post_quality(data["post"])
            except Exception as exc:  # pragma: no cover - exercised in benchmark smoke path
                error = str(exc)
        return self._build_attempt_record(
            task="post",
            model=model,
            candidate=candidate,
            sample_path=None,
            iteration=iteration,
            latency_ms=latency_ms,
            raw_text=raw_text,
            json_success=json_success,
            schema_success=schema_success,
            error=error,
            quality=quality,
        )

    def _build_attempt_record(
        self,
        *,
        task: str,
        model: str,
        candidate: BenchmarkCandidate,
        sample_path: Path | None,
        iteration: int,
        latency_ms: float,
        raw_text: str,
        json_success: bool,
        schema_success: bool,
        error: str,
        quality: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        return {
            "task": task,
            "model": model,
            "candidate": asdict(candidate),
            "sample_path": str(sample_path) if sample_path else None,
            "iteration": iteration,
            "latency_ms": round(latency_ms, 2),
            "json_success": json_success,
            "schema_success": schema_success,
            "error": error,
            "raw_preview": raw_text[:240],
            "quality": quality
            or {
                "format_valid": 0.0,
                "actionable": 0.0,
                "specificity": 0.0,
                "photo_relevance": 0.0,
                "language_quality": 0.0,
                "average": 0.0,
            },
        }

    def _summarize_attempts(self, attempts: list[dict[str, Any]]) -> dict[str, Any]:
        if not attempts:
            return {
                "attempt_count": 0,
                "json_success_rate": 0.0,
                "schema_success_rate": 0.0,
                "average_latency_ms": 0.0,
                "quality_average": 0.0,
                "failure_examples": [],
            }
        json_success_rate = sum(1 for attempt in attempts if attempt["json_success"]) / len(
            attempts
        )
        schema_success_rate = sum(1 for attempt in attempts if attempt["schema_success"]) / len(
            attempts
        )
        average_latency_ms = sum(attempt["latency_ms"] for attempt in attempts) / len(attempts)
        quality_average = sum(attempt["quality"]["average"] for attempt in attempts) / len(attempts)
        failures = [
            {
                "iteration": attempt["iteration"],
                "error": attempt["error"],
                "raw_preview": attempt["raw_preview"],
            }
            for attempt in attempts
            if not attempt["schema_success"]
        ][:3]
        return {
            "attempt_count": len(attempts),
            "json_success_rate": round(json_success_rate, 4),
            "schema_success_rate": round(schema_success_rate, 4),
            "average_latency_ms": round(average_latency_ms, 2),
            "quality_average": round(quality_average, 2),
            "failure_examples": failures,
        }

    def _score_post_quality(self, post_text: str) -> dict[str, float]:
        stripped = post_text.strip()
        sentences = [segment for segment in re.split(r"(?<=[。！？])", stripped) if segment.strip()]
        lowered = stripped.lower()
        chinese_chars = sum(1 for ch in stripped if "\u4e00" <= ch <= "\u9fff")
        format_valid = float(
            bool(stripped) and lowered not in _PLACEHOLDER_TOKENS and chinese_chars >= 4
        )
        actionable = float(any(token in stripped for token in _ACTIONABLE_TOKENS))
        specificity_hits = sum(1 for token in _SPECIFIC_TOKENS if token in stripped)
        specificity = float(
            specificity_hits >= 2 or (len(stripped) >= 14 and specificity_hits >= 1)
        )
        photo_relevance = float(
            any(
                token in stripped
                for token in (
                    "阴影",
                    "高光",
                    "偏色",
                    "锐化",
                    "降噪",
                    "背景",
                    "裁切",
                    "主体",
                    "色调",
                )
            )
        )
        language_quality = float(
            bool(re.search(r"[。！？]$", stripped))
            and 1 <= len(sentences) <= 3
            and chinese_chars >= max(4, len(stripped) // 5)
        )
        average = round(
            format_valid + actionable + specificity + photo_relevance + language_quality,
            2,
        )
        return {
            "format_valid": format_valid,
            "actionable": actionable,
            "specificity": specificity,
            "photo_relevance": photo_relevance,
            "language_quality": language_quality,
            "average": average,
        }

    def _resolve_sample_paths(self, mode: str, sample_set: list[str] | None) -> list[Path]:
        if mode == "single_fixture":
            if not sample_set:
                fixture = (
                    Path(__file__).resolve().parents[3]
                    / "tests"
                    / "fixtures"
                    / "omlx_live_sample.jpg"
                )
                if not fixture.exists():
                    raise FileNotFoundError(f"Default OMLX live fixture is missing: {fixture}")
                return [fixture]
            return [self._resolve_image_candidates(sample_set)[0]]

        if not sample_set:
            raise ValueError(
                "kv_cache_batch mode requires --sample-set with 5 to 10 image paths or directories"
            )
        resolved = self._resolve_image_candidates(sample_set)
        if len(resolved) < 5:
            raise ValueError("kv_cache_batch mode requires at least 5 images")
        return resolved[:10]

    def _resolve_image_candidates(self, sample_set: list[str]) -> list[Path]:
        candidates: list[Path] = []
        for raw_path in sample_set:
            path = Path(raw_path).expanduser().resolve()
            if path.is_dir():
                candidates.extend(
                    sorted(
                        image_path
                        for image_path in path.iterdir()
                        if image_path.is_file() and image_path.suffix.lower() in _IMAGE_EXTENSIONS
                    )
                )
            elif path.is_file():
                candidates.append(path)
            else:
                raise FileNotFoundError(f"Sample path does not exist: {path}")
        deduped: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            deduped.append(candidate)
        if not deduped:
            raise ValueError("No image files were found in the provided sample set")
        return deduped

    def _load_image_bytes(self, path: Path, *, max_edge: int, jpeg_quality: int) -> bytes:
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError(f"Image fixture is unreadable: {path}")
        height, width = image.shape[:2]
        longest = max(height, width)
        if max_edge > 0 and longest > max_edge:
            scale = max_edge / float(longest)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)
        quality = min(100, max(1, int(jpeg_quality)))
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError(f"Failed to encode JPEG bytes for benchmark sample: {path}")
        return encoded.tobytes()

    def _resolve_result_root(self, result_path: str | None) -> Path:
        if result_path:
            return Path(result_path).expanduser().resolve()
        return (Path.cwd() / "artifacts" / "benchmarks" / "omlx").resolve()

    def _build_runtime_contract_support(self, preflight_status: dict[str, Any]) -> dict[str, Any]:
        xgrammar = bool(preflight_status.get("xgrammar", False))
        structured_outputs = bool(preflight_status.get("structured_outputs", False))
        return {
            "server_version": preflight_status.get("version"),
            "xgrammar_available": xgrammar,
            "structured_outputs_available": structured_outputs,
            "response_format_json_schema_path": (
                "grammar_constrained"
                if xgrammar
                else "prompt_injection_and_post_parse"
            ),
            "structured_outputs_path": (
                "grammar_constrained"
                if structured_outputs or xgrammar
                else "not_available"
            ),
        }

    def _describe_contract_execution(
        self,
        candidate: BenchmarkCandidate,
        preflight_status: dict[str, Any],
    ) -> dict[str, Any]:
        support = self._build_runtime_contract_support(preflight_status)
        requested = candidate.contract_mode
        if requested == "response_format_json_schema":
            if support["xgrammar_available"]:
                effective = "grammar_constrained_json_schema"
                note = "response_format json_schema is backed by xgrammar on this runtime."
            else:
                effective = "prompt_injection_and_post_parse"
                note = (
                    "response_format json_schema falls back to JSON-only prompt injection "
                    "plus post-parse validation on this runtime."
                )
        elif requested == "structured_outputs":
            if support["structured_outputs_available"]:
                effective = "grammar_constrained_json_schema"
                note = "structured_outputs json schema is backed by xgrammar on this runtime."
            else:
                effective = "not_available"
                note = (
                    "structured_outputs is not available on this runtime, so JSON success is "
                    "expected to fail before prompt tuning can help."
                )
        else:
            effective = "unknown"
            note = f"Unrecognized contract_mode={requested!r}"

        return {
            "requested_contract_mode": requested,
            "effective_constraint_path": effective,
            "server_version": support["server_version"],
            "xgrammar_available": support["xgrammar_available"],
            "structured_outputs_available": support["structured_outputs_available"],
            "note": note,
        }

    def _benchmark_status(self, config: dict) -> dict[str, Any]:
        benchmark_config = copy.deepcopy(config)
        omlx = benchmark_config.setdefault("omlx", {})
        runtime = omlx.setdefault("runtime", {})
        runtime["probe_on_run"] = False
        runtime["enforce_dedicated_instance"] = False
        runtime["require_structured_outputs"] = False
        runtime["require_xgrammar"] = False
        return OMLXInstanceService().status(benchmark_config)

    def _collect_best_by_model(
        self, results: list[dict[str, Any]], mode: str
    ) -> dict[str, dict[str, Any]]:
        best: dict[str, dict[str, Any]] = {}
        for result in results:
            model = result["model"]
            current_best = best.get(model)
            if current_best is None or tuple(result["best_rank_key"]) > tuple(
                current_best["best_rank_key"]
            ):
                best[model] = result
        return best

    def _update_best_candidates(
        self, best_path: Path, best_by_model: dict[str, dict[str, Any]], mode: str
    ) -> None:
        if best_path.exists():
            existing = json.loads(best_path.read_text(encoding="utf-8"))
        else:
            existing = {}
        for model, summary in best_by_model.items():
            existing_mode = existing.setdefault(model, {})
            current_best = existing_mode.get(mode)
            if current_best is None or tuple(summary["best_rank_key"]) > tuple(
                current_best["best_rank_key"]
            ):
                existing_mode[mode] = summary
        best_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
