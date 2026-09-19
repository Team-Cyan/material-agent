import time
import sys
import json
import resource
import os
from pathlib import Path

start = time.perf_counter()
root = Path.cwd()
source = Path(sys.argv[1]).resolve()
profile = sys.argv[2]
out = Path(sys.argv[3])
sys.path.insert(0, str(source / "src"))


# Fail closed on media writes, production DB construction or external metadata writers.
def audit(event, args):
    if event == "open":
        p, mode, flags = args
        if isinstance(p, (str, bytes, os.PathLike)) and (flags or 0) & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC
        ):
            if Path(os.fsdecode(p)).suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
                ".xmp",
                ".dng",
                ".arw",
                ".cr2",
                ".db",
            }:
                raise RuntimeError("forbidden write")
    if event == "subprocess.Popen" and "exiftool" in str(args):
        raise RuntimeError("forbidden external writer")


sys.addaudithook(audit)
import yaml  # noqa: E402 -- import measured after source selection and write guard
from material_agent.app import local_benchmark_service as b  # noqa: E402

assert Path(b.__file__).resolve().is_relative_to(source)
config = yaml.safe_load(
    (
        root / ("config.yaml" if profile == "heuristic" else "docker/config.intel-openvino.yaml")
    ).read_text()
)
c = {
    **config.get("local", {}),
    "inference": {"runtime": "cpu"},
    "preview": config.get("preview", {}),
}
if profile == "intel":
    assets = root / ".local/inference-unification/assets"
    c["detection"].update(
        model_path=str(assets / "ssd.onnx"),
        face_model_path=str(assets / "yunet.onnx"),
        compiled_cache_dir=str(out.resolve() / "compiled-cache"),
    )
    c["aesthetic"].update(model_path=str(assets / "nima.tflite"), compiled_cache_dir=str(out.resolve() / "compiled-cache"))
if profile == "intel":
    assert not (out.resolve() / "compiled-cache").exists(), "use a fresh output directory"
counts = {}


def instrument(cls, name, key):
    old = getattr(cls, name)

    def wrapped(*args, **kwargs):
        counts[key] = counts.get(key, 0) + 1
        return old(*args, **kwargs)

    setattr(cls, name, wrapped)


if profile == "intel":
    from material_agent.adapters.models import (
        openvino_nima_aesthetic as n,
        openvino_ssd_detection as d,
    )

    instrument(n._OpenVinoNimaRuntime, "__init__", "nima_init")
    instrument(d._OpenVinoSsdRuntime, "__init__", "ssd_init")
    instrument(n.OpenVinoNimaAestheticAdapter, "_score_many_sync", "nima_adapter_calls")
    instrument(d.OpenVinoSsdObjectDetectorAdapter, "_detect_sync", "detection_calls")
old = b._load_benchmark_image


def load(*args, **kw):
    counts["input_loads"] = counts.get("input_loads", 0) + 1
    return old(*args, **kw)


b._load_benchmark_image = load
import_seconds = time.perf_counter() - start
_, _, report = b.run_local_benchmark(
    root / "tests/fixtures/local_benchmark/manifest.yaml", out, repeat_count=5, client_config=c
)
metrics = report["metrics"]
scores = [
    {
        "id": r.get("id", r.get("item_id")),
        "dimensions": r.get("dimensions"),
        "score": r.get("score"),
        "scene": r.get("scene"),
        "aesthetic_score": (r.get("aesthetic") or {}).get("score"),
    }
    for r in report["items"]
]
print(
    json.dumps(
        {
            "profile": profile,
            "source": str(source),
            "import_seconds": import_seconds,
            "child_elapsed_seconds": time.perf_counter() - start,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "metrics": metrics,
            "counts": counts,
            "scores": scores,
        }
    )
)
