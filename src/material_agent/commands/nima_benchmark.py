from __future__ import annotations

import json

from ..app.nima_device_benchmark import run_nima_device_benchmark


def cmd_benchmark_nima_device(args) -> int:
    report = run_nima_device_benchmark(
        args.input_dir,
        args.model_path,
        args.output_dir,
        devices=[value.strip() for value in args.devices.split(",") if value.strip()],
        batch_sizes=[int(value) for value in args.batch_sizes.split(",") if value.strip()],
        max_files=args.max_files,
        warm_repetitions=args.warm_repetitions,
    )
    print(json.dumps(report["selected"], indent=2))
    return 0 if report["selected"] else 1
