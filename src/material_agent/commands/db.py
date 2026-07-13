from pathlib import Path

from ..app.scene_service import SceneDbService
from ..utils.constants import SCENE_LIST
from ..utils.run_control import exclusive_run_lock
from ..utils.runtime_paths import ensure_runtime_paths


def _db_path(input_dir: str) -> Path:
    return ensure_runtime_paths(input_dir).db_path


def cmd_scan_scenes(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1
    grouped = SceneDbService().scan_distribution(args.dir)
    ordered = (["other"] if "other" in grouped else []) + sorted(key for key in grouped if key != "other")
    for scene in ordered:
        total = sum(count for _, count in grouped[scene])
        print(f"\n[{scene}] ({total} photos)")
        for raw, cnt in grouped[scene][:20]:
            print(f"  {cnt:4d}x  {raw}")
        if len(grouped[scene]) > 20:
            print(f"       ... and {len(grouped[scene]) - 20} more")
    return 0


def cmd_remap_scenes(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1
    valid = set(SCENE_LIST)
    with exclusive_run_lock(db_path.parent / "run.lock"):
        try:
            target_scene, count = SceneDbService().remap_scene(
                args.dir, from_raw=args.from_, to_display=args.to
            )
        except KeyError:
            print(f"Error: '{args.to}' not valid. Choose from: {SCENE_LIST}")
            return 2
    if target_scene not in valid:
        print(f"Error: '{args.to}' not valid. Choose from: {SCENE_LIST}")
        return 2
    print(f"Updated {count} rows: scene_raw='{args.from_}' -> scene='{target_scene}'")
    return 0

def cmd_suggest_scenes(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1
    limit = getattr(args, "limit", 20)
    min_count = getattr(args, "min_count", 2)
    suggestions = SceneDbService().suggest_scenes(args.dir, limit=limit, min_count=min_count)

    if not suggestions:
        print("No scene suggestions found.")
        return 0

    print("Scene suggestions for current 'other' items:")
    for scene_raw, cnt, suggested_scene in suggestions:
        print(f"  {cnt:4d}x  {scene_raw}  ->  {suggested_scene}")
    return 0


def cmd_fix_db(args):
    db_path = _db_path(args.dir)
    if not db_path.exists():
        print(f"Error: no database found at {db_path}")
        return 1
    with exclusive_run_lock(db_path.parent / "run.lock"):
        summary = SceneDbService().fix_db(args.dir)
    print(
        f"fix-db done:\n"
        f"  star_rating repaired : {summary['star_rating_repaired']}\n"
        f"  group info repaired  : {summary['group_info_repaired']}\n"
        f"  scene migrated       : {summary['scene_migrated']}\n"
        f"  bad scene_raw cleared: {summary['bad_scene_raw_cleared']}"
    )
    return 0
