from types import SimpleNamespace

from material_agent.app import nima_device_benchmark as module


def test_nima_device_benchmark_selects_fastest_profile(tmp_path, monkeypatch):
    source = tmp_path / "photos"
    source.mkdir()
    raw = source / "one.ARW"
    raw.write_bytes(b"raw")
    model = tmp_path / "nima.tflite"
    model.write_bytes(b"model")
    monkeypatch.setattr(module, "scan_arw_files", lambda *_args: [str(raw)])
    monkeypatch.setattr(
        module,
        "decode_raw",
        lambda *_args: SimpleNamespace(jpeg_bytes=b"jpeg"),
    )

    def profile(_images, _model, _cache, *, device, batch_size, warm_repetitions):
        seconds = 1.0 if device == "CPU" else 2.0
        return {
            "device": device,
            "batch_size": batch_size,
            "warm_p50_seconds": seconds,
            "warm_images_per_second": 1.0 / seconds,
            "execution_devices": [device],
        }

    monkeypatch.setattr(module, "_run_profile", profile)
    report = module.run_nima_device_benchmark(
        source,
        model,
        tmp_path / "output",
        devices=["CPU", "GPU.0"],
        batch_sizes=[1],
        warm_repetitions=2,
    )

    assert report["selected"]["device"] == "CPU"
    assert (tmp_path / "output" / "nima-device-benchmark.json").is_file()
    assert (tmp_path / "output" / "nima-device-benchmark.md").is_file()


def test_nima_device_benchmark_keeps_device_failure_in_report(tmp_path, monkeypatch):
    source = tmp_path / "photos"
    source.mkdir()
    raw = source / "one.ARW"
    raw.write_bytes(b"raw")
    model = tmp_path / "nima.tflite"
    model.write_bytes(b"model")
    monkeypatch.setattr(module, "scan_arw_files", lambda *_args: [str(raw)])
    monkeypatch.setattr(
        module,
        "decode_raw",
        lambda *_args: SimpleNamespace(jpeg_bytes=b"jpeg"),
    )
    monkeypatch.setattr(
        module,
        "_run_profile",
        lambda *_args, device, batch_size, **_kwargs: {
            "device": device,
            "batch_size": batch_size,
            "files": 1,
            "error": "device unavailable",
        },
    )

    report = module.run_nima_device_benchmark(
        source,
        model,
        tmp_path / "output",
        devices=["GPU.0"],
        batch_sizes=[1],
    )
    assert report["selected"] is None
    assert report["profiles"][0]["error"] == "device unavailable"
