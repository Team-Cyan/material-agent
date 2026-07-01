import argparse

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


def configure_run_parser(parser) -> None:
    parser.add_argument("input_dir", help="Directory containing RAW files")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Score files but skip writing XMP and DB",
    )
    parser.add_argument("--scorers")
    parser.add_argument(
        "--no-visual-merge",
        action="store_true",
        dest="no_visual_merge",
        help="Disable visual similarity merge (faster restarts)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="material-agent: NAS-first local photo scorer")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Score photos")
    configure_run_parser(p_run)

    p_scan = sub.add_parser("scan-scenes", help="Show scene_raw distribution")
    p_scan.add_argument("--dir", required=True)

    p_suggest = sub.add_parser("suggest-scenes", help="Suggest scene remaps from scene_raw")
    p_suggest.add_argument("--dir", required=True)
    p_suggest.add_argument("--limit", type=int, default=20)
    p_suggest.add_argument("--min-count", type=int, default=2, dest="min_count")

    p_remap = sub.add_parser("remap-scenes", help="Remap scene_raw to scene")
    p_remap.add_argument("--dir", required=True)
    p_remap.add_argument("--from", required=True, dest="from_")
    p_remap.add_argument("--to", required=True)

    p_rescore = sub.add_parser("rescore", help="Recalculate scores from stored dimensions")
    p_rescore.add_argument("--dir", required=True)
    p_rescore.add_argument("--config", default="config.yaml")
    p_rescore.add_argument(
        "--scene", nargs="+", metavar="SCENE", help="Only rescore files with these scene values"
    )

    p_rewrite = sub.add_parser("rewrite-xmp", help="Force-rewrite all XMP sidecars from DB")
    p_rewrite.add_argument("--dir", required=True)
    p_rewrite.add_argument("--config", default="config.yaml")
    p_rewrite.add_argument("--dry-run", action="store_true", dest="dry_run")

    p_rewrite_commentary = sub.add_parser(
        "rewrite-commentary",
        help="Regenerate commentary from stored scores and optionally rewrite XMP descriptions",
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
    )
    p_reset_ai.add_argument("--dir", required=True)
    p_reset_ai.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_reset_ai.add_argument(
        "--keep-xmp",
        action="store_true",
        dest="keep_xmp",
        help="Only clear database AI state and keep existing XMP sidecars untouched",
    )

    p_fix = sub.add_parser("fix-db", help="Repair data quality issues in the database")
    p_fix.add_argument("--dir", required=True)
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "scan-scenes":
        cmd_scan_scenes(args)
    elif args.command == "suggest-scenes":
        cmd_suggest_scenes(args)
    elif args.command == "remap-scenes":
        cmd_remap_scenes(args)
    elif args.command == "rescore":
        cmd_rescore(args, load_config(args.config))
    elif args.command == "rewrite-xmp":
        cmd_rewrite_xmp(args)
    elif args.command == "rewrite-commentary":
        cmd_rewrite_commentary(args)
    elif args.command == "reset-ai":
        cmd_reset_ai(args)
    elif args.command == "fix-db":
        cmd_fix_db(args)
    elif args.command == "run":
        cmd_run(args, load_raw_config(args.config))
    else:
        parser.print_help()
