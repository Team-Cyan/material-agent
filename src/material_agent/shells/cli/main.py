import argparse
import sys

from ...app.errors import RunCancelled

def load_raw_config(path: str) -> dict:
    from ...commands.scoring import load_raw_config as _load_raw_config

    return _load_raw_config(path)


def load_config(path: str) -> dict:
    from ...commands.scoring import load_config as _load_config

    return _load_config(path)


def cmd_run(args, config):
    from ...commands.scoring import cmd_run as _cmd_run

    return _cmd_run(args, config)


def cmd_rescore(args, config):
    from ...commands.scoring import cmd_rescore as _cmd_rescore

    return _cmd_rescore(args, config)


def cmd_rewrite_xmp(args):
    from ...commands.io import cmd_rewrite_xmp as _cmd_rewrite_xmp

    return _cmd_rewrite_xmp(args)


def cmd_rewrite_commentary(args):
    from ...commands.io import cmd_rewrite_commentary as _cmd_rewrite_commentary

    return _cmd_rewrite_commentary(args)


def cmd_reset_ai(args):
    from ...commands.io import cmd_reset_ai as _cmd_reset_ai

    return _cmd_reset_ai(args)


def cmd_scan_scenes(args):
    from ...commands.db import cmd_scan_scenes as _cmd_scan_scenes

    return _cmd_scan_scenes(args)


def cmd_suggest_scenes(args):
    from ...commands.db import cmd_suggest_scenes as _cmd_suggest_scenes

    return _cmd_suggest_scenes(args)


def cmd_remap_scenes(args):
    from ...commands.db import cmd_remap_scenes as _cmd_remap_scenes

    return _cmd_remap_scenes(args)


def cmd_fix_db(args):
    from ...commands.db import cmd_fix_db as _cmd_fix_db

    return _cmd_fix_db(args)


def cmd_benchmark_local(args):
    from ...commands.benchmark import cmd_benchmark_local as _cmd_benchmark_local

    return _cmd_benchmark_local(args)


def cmd_prepare_openvino_model(args):
    from ...commands.benchmark import cmd_prepare_openvino_model as _cmd_prepare_openvino_model

    return _cmd_prepare_openvino_model(args)


def cmd_fit_aesthetic_calibration(args):
    from ...commands.benchmark import (
        cmd_fit_aesthetic_calibration as _cmd_fit_aesthetic_calibration,
    )

    return _cmd_fit_aesthetic_calibration(args)


def cmd_models(args):
    from ...commands.models import cmd_models as _cmd_models

    return _cmd_models(args)


def cmd_aesthetic_labels(args):
    from ...commands.aesthetic_labels import cmd_aesthetic_labels as _cmd_aesthetic_labels

    return _cmd_aesthetic_labels(args)


def cmd_benchmark_nima_device(args):
    from ...commands.nima_benchmark import cmd_benchmark_nima_device as _command

    return _command(args)


def configure_run_parser(parser) -> None:
    parser.add_argument("input_dir", help="Directory containing RAW files")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Score files without XMP/processed writes; runtime job state is still recorded",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        dest="allow_empty",
        help="Allow a successful run when no configured photo files are discovered",
    )
    parser.add_argument("--scorers")
    parser.add_argument(
        "--no-visual-merge",
        action="store_true",
        dest="no_visual_merge",
        help="Disable visual similarity merge (faster restarts)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="material-agent: NAS-first local photo scorer",
        allow_abbrev=False,
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Score photos", allow_abbrev=False)
    configure_run_parser(p_run)

    p_benchmark = sub.add_parser(
        "benchmark-local",
        help="Run an isolated local heuristic benchmark from a fixture manifest",
        allow_abbrev=False,
    )
    p_benchmark.add_argument("--manifest", required=True)
    p_benchmark.add_argument("--output-dir", required=True, dest="output_dir")
    p_benchmark.add_argument(
        "--config",
        help="Optional local backend config used to enable benchmark model blocks",
    )

    p_prepare_openvino = sub.add_parser(
        "prepare-openvino-model",
        help="Materialize an ONNX external-data bundle for native OpenVINO loading",
        allow_abbrev=False,
    )
    p_prepare_openvino.add_argument("--source-model", required=True, dest="source_model")
    p_prepare_openvino.add_argument(
        "--source-processor", required=True, dest="source_processor"
    )
    p_prepare_openvino.add_argument("--output-dir", required=True, dest="output_dir")
    p_fit_calibration = sub.add_parser(
        "fit-aesthetic-calibration",
        help="Fit target-specific NIMA calibration profiles from human labels",
        allow_abbrev=False,
    )
    p_fit_calibration.add_argument("--labels", required=True)
    p_fit_calibration.add_argument("--output", required=True)
    p_fit_calibration.add_argument("--report")
    p_fit_calibration.add_argument(
        "--minimum-label-count", type=int, default=20, dest="minimum_label_count"
    )
    p_fit_calibration.add_argument(
        "--minimum-raw-span", type=float, default=1.0, dest="minimum_raw_span"
    )
    p_fit_calibration.add_argument("--pivot", type=float, default=5.5)
    p_fit_calibration.add_argument(
        "--policy-version", default="target-affine-v1", dest="policy_version"
    )
    p_models = sub.add_parser(
        "models",
        help="List, install, select, delete, or serve managed local models",
        allow_abbrev=False,
    )
    p_models.add_argument(
        "--registry-dir",
        default="~/.material-agent/models",
        dest="registry_dir",
    )
    p_models.add_argument(
        "--catalog",
        help="Optional operator-managed JSON catalog of adapter-compatible models",
    )
    models_sub = p_models.add_subparsers(dest="models_command", required=True)
    models_sub.add_parser("list", allow_abbrev=False)
    for action in ("install", "select"):
        child = models_sub.add_parser(action, allow_abbrev=False)
        child.add_argument("model_id")
    p_models_delete = models_sub.add_parser("delete", allow_abbrev=False)
    p_models_delete.add_argument("model_id")
    p_models_delete.add_argument("--force", action="store_true")
    p_models_serve = models_sub.add_parser("serve", allow_abbrev=False)
    p_models_serve.add_argument("--host", default="127.0.0.1")
    p_models_serve.add_argument("--port", type=int, default=8765)
    p_models_serve.add_argument("--token-file", dest="token_file")
    p_labels = sub.add_parser(
        "aesthetic-labels",
        help="Import, export, and inspect the local human-aesthetic label store",
        allow_abbrev=False,
    )
    p_labels.add_argument("--database", required=True)
    labels_sub = p_labels.add_subparsers(dest="labels_command", required=True)
    p_labels_import = labels_sub.add_parser("import", allow_abbrev=False)
    p_labels_import.add_argument("--input", required=True)
    p_labels_import.add_argument(
        "--holdout-percent", type=int, default=20, dest="holdout_percent"
    )
    p_labels_export = labels_sub.add_parser("export", allow_abbrev=False)
    p_labels_export.add_argument("--output", required=True)
    p_labels_export.add_argument("--split", choices=("train", "holdout"))
    labels_sub.add_parser("stats", allow_abbrev=False)
    p_nima_benchmark = sub.add_parser(
        "benchmark-nima-device",
        help="Benchmark the bundled NIMA graph across OpenVINO devices and batches",
        allow_abbrev=False,
    )
    p_nima_benchmark.add_argument("--input-dir", required=True, dest="input_dir")
    p_nima_benchmark.add_argument("--model-path", required=True, dest="model_path")
    p_nima_benchmark.add_argument("--output-dir", required=True, dest="output_dir")
    p_nima_benchmark.add_argument("--devices", default="CPU,GPU.0")
    p_nima_benchmark.add_argument("--batch-sizes", default="1,4,8", dest="batch_sizes")
    p_nima_benchmark.add_argument("--max-files", type=int, default=128, dest="max_files")
    p_nima_benchmark.add_argument(
        "--warm-repetitions", type=int, default=5, dest="warm_repetitions"
    )
    p_benchmark.add_argument("--repeat-count", type=int, default=2, dest="repeat_count")
    p_benchmark.add_argument(
        "--reject-threshold", type=float, default=4.0, dest="reject_threshold"
    )
    p_benchmark.add_argument(
        "--quality-reject-threshold",
        type=float,
        default=5.0,
        dest="quality_reject_threshold",
    )

    p_scan = sub.add_parser(
        "scan-scenes", help="Show scene_raw distribution", allow_abbrev=False
    )
    p_scan.add_argument("--dir", required=True)

    p_suggest = sub.add_parser(
        "suggest-scenes",
        help="Suggest scene remaps from scene_raw",
        allow_abbrev=False,
    )
    p_suggest.add_argument("--dir", required=True)
    p_suggest.add_argument("--limit", type=int, default=20)
    p_suggest.add_argument("--min-count", type=int, default=2, dest="min_count")

    p_remap = sub.add_parser(
        "remap-scenes", help="Remap scene_raw to scene", allow_abbrev=False
    )
    p_remap.add_argument("--dir", required=True)
    p_remap.add_argument("--from", required=True, dest="from_")
    p_remap.add_argument("--to", required=True)

    p_rescore = sub.add_parser(
        "rescore",
        help="Recalculate scores from stored dimensions",
        allow_abbrev=False,
    )
    p_rescore.add_argument("--dir", required=True)
    p_rescore.add_argument("--config", default="config.yaml")
    p_rescore.add_argument(
        "--scene", nargs="+", metavar="SCENE", help="Only rescore files with these scene values"
    )

    p_rewrite = sub.add_parser(
        "rewrite-xmp",
        help="Force-rewrite all XMP sidecars from DB",
        allow_abbrev=False,
    )
    p_rewrite.add_argument("--dir", required=True)
    p_rewrite.add_argument("--config", default="config.yaml")
    p_rewrite.add_argument("--dry-run", action="store_true", dest="dry_run")

    p_rewrite_commentary = sub.add_parser(
        "rewrite-commentary",
        help="Regenerate commentary from stored scores and optionally rewrite XMP descriptions",
        allow_abbrev=False,
    )
    p_rewrite_commentary.add_argument("--dir", required=True)
    p_rewrite_commentary.add_argument("--config", default="config.yaml")
    p_rewrite_commentary.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_rewrite_commentary.add_argument(
        "--rewrite-xmp",
        action="store_true",
        dest="rewrite_xmp",
        help="Also rewrite XMP descriptions after DB commentary is updated",
    )

    p_reset_ai = sub.add_parser(
        "reset-ai",
        help="Clear AI-derived scores/commentary state while preserving non-AI caches",
        allow_abbrev=False,
    )
    p_reset_ai.add_argument("--dir", required=True)
    p_reset_ai.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_reset_ai.add_argument(
        "--clear-xmp",
        action="store_true",
        dest="clear_xmp",
        help="Also clear AI-managed XMP fields; existing XMP is preserved by default",
    )
    p_reset_ai.add_argument(
        "--keep-xmp",
        action="store_false",
        dest="clear_xmp",
        help=argparse.SUPPRESS,
    )
    p_reset_ai.set_defaults(clear_xmp=False)

    p_fix = sub.add_parser(
        "fix-db", help="Repair data quality issues in the database", allow_abbrev=False
    )
    p_fix.add_argument("--dir", required=True)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "benchmark-local":
            return cmd_benchmark_local(args)
        if args.command == "prepare-openvino-model":
            return cmd_prepare_openvino_model(args)
        if args.command == "fit-aesthetic-calibration":
            return cmd_fit_aesthetic_calibration(args)
        if args.command == "models":
            return cmd_models(args)
        if args.command == "aesthetic-labels":
            return cmd_aesthetic_labels(args)
        if args.command == "benchmark-nima-device":
            return cmd_benchmark_nima_device(args)
        if args.command == "scan-scenes":
            return cmd_scan_scenes(args)
        if args.command == "suggest-scenes":
            return cmd_suggest_scenes(args)
        if args.command == "remap-scenes":
            return cmd_remap_scenes(args)
        if args.command == "rescore":
            return cmd_rescore(args, load_config(args.config))
        if args.command == "rewrite-xmp":
            return cmd_rewrite_xmp(args)
        if args.command == "rewrite-commentary":
            return cmd_rewrite_commentary(args)
        if args.command == "reset-ai":
            return cmd_reset_ai(args)
        if args.command == "fix-db":
            return cmd_fix_db(args)
        if args.command == "run":
            return cmd_run(args, load_raw_config(args.config))
        parser.print_help()
        return 0
    except RunCancelled as error:
        print(f"Run cancelled: {error}", file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        print("Run cancelled by operator", file=sys.stderr)
        return 130
    except (OSError, ValueError) as error:
        parser.error(str(error))
