from __future__ import annotations

from pathlib import Path

from ..app.web_service import serve_web


def cmd_web(args) -> int:
    token = None
    if args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        if not token:
            raise ValueError("Web UI token file is empty")
    serve_web(
        host=args.host,
        port=args.port,
        token=token,
        input_root=args.input_dir,
        config_path=args.config,
        work_dir=args.work_dir,
        registry_dir=args.registry_dir,
        catalog_path=args.catalog,
    )
    return 0
