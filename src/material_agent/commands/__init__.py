def cmd_fix_db(*args, **kwargs):
    from .db import cmd_fix_db as _cmd_fix_db

    return _cmd_fix_db(*args, **kwargs)


def cmd_remap_scenes(*args, **kwargs):
    from .db import cmd_remap_scenes as _cmd_remap_scenes

    return _cmd_remap_scenes(*args, **kwargs)


def cmd_scan_scenes(*args, **kwargs):
    from .db import cmd_scan_scenes as _cmd_scan_scenes

    return _cmd_scan_scenes(*args, **kwargs)


def cmd_suggest_scenes(*args, **kwargs):
    from .db import cmd_suggest_scenes as _cmd_suggest_scenes

    return _cmd_suggest_scenes(*args, **kwargs)


def cmd_rewrite_xmp(*args, **kwargs):
    from .io import cmd_rewrite_xmp as _cmd_rewrite_xmp

    return _cmd_rewrite_xmp(*args, **kwargs)


def cmd_rewrite_commentary(*args, **kwargs):
    from .io import cmd_rewrite_commentary as _cmd_rewrite_commentary

    return _cmd_rewrite_commentary(*args, **kwargs)


def cmd_reset_ai(*args, **kwargs):
    from .io import cmd_reset_ai as _cmd_reset_ai

    return _cmd_reset_ai(*args, **kwargs)


def cmd_setup_omlx(*args, **kwargs):
    from .omlx_runtime import cmd_setup_omlx as _cmd_setup_omlx

    return _cmd_setup_omlx(*args, **kwargs)


def cmd_start_omlx(*args, **kwargs):
    from .omlx_runtime import cmd_start_omlx as _cmd_start_omlx

    return _cmd_start_omlx(*args, **kwargs)


def cmd_status_omlx(*args, **kwargs):
    from .omlx_runtime import cmd_status_omlx as _cmd_status_omlx

    return _cmd_status_omlx(*args, **kwargs)


def cmd_rescore(*args, **kwargs):
    from .scoring import cmd_rescore as _cmd_rescore

    return _cmd_rescore(*args, **kwargs)


def cmd_run(*args, **kwargs):
    from .scoring import cmd_run as _cmd_run

    return _cmd_run(*args, **kwargs)


def configure_run_parser(*args, **kwargs):
    from ..shells.cli.main import configure_run_parser as _configure_run_parser

    return _configure_run_parser(*args, **kwargs)


def load_config(*args, **kwargs):
    from .scoring import load_config as _load_config

    return _load_config(*args, **kwargs)

__all__ = [
    "cmd_fix_db",
    "cmd_remap_scenes",
    "cmd_rewrite_commentary",
    "cmd_reset_ai",
    "cmd_rewrite_xmp",
    "cmd_rescore",
    "cmd_run",
    "cmd_scan_scenes",
    "cmd_setup_omlx",
    "cmd_start_omlx",
    "cmd_status_omlx",
    "cmd_suggest_scenes",
    "configure_run_parser",
    "load_config",
]
