import yaml

from material_agent.app.aesthetic_label_store import AestheticLabelStore


def test_label_store_import_stats_and_split_export(tmp_path):
    labels = tmp_path / "labels.yaml"
    labels.write_text(
        yaml.safe_dump(
            {
                "items": [
                    {
                        "path": "a.ARW",
                        "target": "Person",
                        "raw_score": 6.0,
                        "human_rating": 4,
                        "split": "train",
                    },
                    {
                        "path": "b.ARW",
                        "target": "person",
                        "raw_score": 5.0,
                        "human_score": 7.0,
                        "split": "holdout",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    store = AestheticLabelStore(tmp_path / "labels.sqlite")

    result = store.import_file(labels)
    assert result["total"] == 2
    assert result["targets"]["person"] == {"train": 1, "holdout": 1, "total": 2}

    output = tmp_path / "holdout.yaml"
    exported = store.export_file(output, split="holdout")
    assert exported["items"] == 1
    payload = yaml.safe_load(output.read_text())
    assert payload["items"][0]["path"] == "b.ARW"


def test_label_store_deterministic_split_is_stable(tmp_path):
    labels = tmp_path / "labels.yaml"
    labels.write_text(
        yaml.safe_dump(
            {
                "items": [
                    {
                        "path": "stable.ARW",
                        "target": "dog",
                        "raw_score": 4.0,
                        "human_score": 6.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = AestheticLabelStore(tmp_path / "labels.sqlite")
    store.import_file(labels)
    first = store.items()[0]["split"]
    store.import_file(labels)
    assert store.items()[0]["split"] == first
