import base64
import contextlib
import json
import sys

from .musiq import MusiqFastScreeningAdapter


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    jpeg_bytes = base64.b64decode(payload["jpeg_base64"])
    adapter = MusiqFastScreeningAdapter(
        {
            "metric": payload.get("metric", "musiq"),
            "device": payload.get("device", "cpu"),
            "score_divisor": float(payload.get("score_divisor", 10.0)),
            "python_bin": "",
        }
    )
    with contextlib.redirect_stdout(sys.stderr):
        score = adapter._score_sync(jpeg_bytes)
    sys.stdout.write(json.dumps({"overall": score}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
