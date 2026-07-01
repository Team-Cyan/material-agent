from material_agent.adapters.progress.rich_sink import RichEventSink


class _FakeProgress:
    def __init__(self):
        self.calls = []

    def on_start(self, total):
        self.calls.append(("on_start", total))

    def on_file_start(self, file_path, index):
        self.calls.append(("on_file_start", file_path, index))

    def on_score_done(self, file_path, score):
        self.calls.append(("on_score_done", file_path, score))

    def on_write_done(self, file_path, score):
        self.calls.append(("on_write_done", file_path, score))

    def on_error(self, file_path, error):
        self.calls.append(("on_error", file_path, str(error)))

    def on_finish(self):
        self.calls.append(("on_finish",))


def test_rich_event_sink_maps_runtime_events_to_progress_callbacks():
    progress = _FakeProgress()
    sink = RichEventSink(progress)

    sink.publish(event_type="job_started", payload={"file_count": 2})
    sink.publish(event_type="job_file_started", payload={"file_path": "/tmp/a.ARW", "index": 1})
    sink.publish(event_type="job_file_scored", payload={"file_path": "/tmp/a.ARW", "score_total": 7.5})
    sink.publish(event_type="job_file_written", payload={"file_path": "/tmp/a.ARW", "score_total": 7.5})
    sink.publish(event_type="job_file_failed", payload={"file_path": "/tmp/b.ARW", "error": "boom"})
    sink.publish(event_type="job_finished", payload={})

    assert progress.calls == [
        ("on_start", 2),
        ("on_file_start", "/tmp/a.ARW", 1),
        ("on_score_done", "/tmp/a.ARW", 7.5),
        ("on_write_done", "/tmp/a.ARW", 7.5),
        ("on_error", "/tmp/b.ARW", "boom"),
        ("on_finish",),
    ]
