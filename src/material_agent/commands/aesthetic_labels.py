from __future__ import annotations

import json

from ..app.aesthetic_label_store import AestheticLabelStore


def cmd_aesthetic_labels(args) -> int:
    store = AestheticLabelStore(args.database)
    if args.labels_command == "import":
        result = store.import_file(args.input, holdout_percent=args.holdout_percent)
    elif args.labels_command == "export":
        result = store.export_file(args.output, split=args.split)
    elif args.labels_command == "stats":
        result = store.stats()
    else:
        raise ValueError("missing aesthetic-labels subcommand")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
