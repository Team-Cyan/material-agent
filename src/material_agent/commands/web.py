from __future__ import annotations

from ..app.web_service import serve_web


def cmd_web(args) -> int:
    serve_web(
        host=args.host,
        port=args.port,
        input_root=args.input_dir,
        config_path=args.config,
        work_dir=args.work_dir,
        registry_dir=args.registry_dir,
        catalog_path=args.catalog,
    )
    return 0
