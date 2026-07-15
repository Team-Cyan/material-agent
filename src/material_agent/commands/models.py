from __future__ import annotations

import json
from pathlib import Path

from ..app.model_api import serve_model_api
from ..app.model_catalog_service import (
    DEFAULT_MODEL_CATALOG,
    ModelCatalogService,
    load_model_catalog,
)


def cmd_models(args) -> int:
    catalog = load_model_catalog(args.catalog) if args.catalog else DEFAULT_MODEL_CATALOG
    service = ModelCatalogService(args.registry_dir, catalog=catalog)
    if args.models_command == "list":
        payload = {"models": service.list_models(), "selections": service.selections()}
    elif args.models_command == "install":
        payload = service.install(args.model_id)
    elif args.models_command == "select":
        payload = service.select(args.model_id)
    elif args.models_command == "delete":
        payload = service.delete(args.model_id, force=args.force)
    elif args.models_command == "serve":
        token = None
        if args.token_file:
            token = Path(args.token_file).read_text(encoding="utf-8").strip()
            if not token:
                raise ValueError("model API token file is empty")
        serve_model_api(service, host=args.host, port=args.port, token=token)
        return 0
    else:
        raise ValueError("missing models subcommand")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0
