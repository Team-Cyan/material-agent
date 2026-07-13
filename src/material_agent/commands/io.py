from pathlib import Path

from ..app.reset_ai_judgement_service import ResetAiJudgementService
from ..app.rewrite_commentary_service import RewriteCommentaryService
from ..app.rewrite_xmp_service import RewriteXmpService
from ..utils.run_control import exclusive_run_lock
from ..utils.runtime_paths import ensure_runtime_paths


def load_config(path: str) -> dict:
    from .scoring import load_config as _load_config

    return _load_config(path)


def _db_path(input_dir: str) -> Path:
    return ensure_runtime_paths(input_dir).db_path


def cmd_rewrite_xmp(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1

    config_path = getattr(args, "config", "config.yaml")
    config = load_config(config_path)
    with exclusive_run_lock(db_path.parent / "run.lock"):
        summary = RewriteXmpService().run(
            args.dir,
            dry_run=args.dry_run,
            output_language=config.get("output_language", "zh"),
        )
    if not args.dry_run:
        print(f"rewrite-xmp: {summary['ok']} written, {summary['err']} errors")
    return 1 if summary.get("err", 0) else 0


def cmd_rewrite_commentary(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1

    config_path = getattr(args, "config", "config.yaml")
    config = load_config(config_path)
    with exclusive_run_lock(db_path.parent / "run.lock"):
        summary = RewriteCommentaryService().run(
            args.dir,
            dry_run=args.dry_run,
            rewrite_xmp=bool(getattr(args, "rewrite_xmp", False)),
            output_language=config.get("output_language", "zh"),
        )
    if args.dry_run:
        print(
            f"rewrite-commentary dry-run: {summary['updated']} of {summary['done_rows']} rows would change"
        )
        return 0
    print(
        f"rewrite-commentary: {summary['updated']} rows updated, "
        f"{summary['rewritten_xmp']} xmp rewritten, "
        f"{summary.get('xmp_errors', 0)} errors"
    )
    return 1 if summary.get("xmp_errors", 0) else 0


def cmd_reset_ai(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1

    with exclusive_run_lock(db_path.parent / "run.lock"):
        summary = ResetAiJudgementService().run(
            args.dir,
            dry_run=bool(getattr(args, "dry_run", False)),
            clear_xmp=bool(getattr(args, "clear_xmp", False)),
        )
    if getattr(args, "dry_run", False):
        print(
            "reset-ai dry-run: "
            f"{summary['files']} files, "
            f"{summary['processed_rows_deleted']} processed rows, "
            f"{summary['signal_rows_deleted']} signal rows, "
            f"{summary['xmp_cleared']} xmp files would be cleared"
        )
        return 0
    print(
        "reset-ai: "
        f"{summary['files']} files reset, "
        f"{summary['processed_rows_deleted']} processed rows deleted, "
        f"{summary['signal_rows_deleted']} signal rows deleted, "
        f"{summary['xmp_cleared']} xmp files cleared"
    )
    return 0
