"""Experiment selection and comparison safeguards; no model or media writes."""
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def experiments(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    return (importlib.import_module('benchmark_mobileclip_candidate'),
            importlib.import_module('benchmark_stanford40_actions'))


def test_action_subset_is_fixed_test_only_and_balanced(tmp_path, monkeypatch, experiments):
    _, actions = experiments
    splits = tmp_path / 'ImageSplits'
    splits.mkdir()
    for index in range(40):
        label = f'action_{index}'
        (splits / f'{label}_train.txt').write_text(f'{label}_001.jpg\n')
        (splits / f'{label}_test.txt').write_text('\n'.join(f'{label}_{i:03}.jpg' for i in range(2, 12)))
    monkeypatch.setattr(actions, 'sha256', lambda path: 'digest')
    selected = actions.select_test_subset(tmp_path)
    assert len(selected) == 200
    assert len({row['file'] for row in selected}) == 200
    assert all(not row['file'].endswith('_001.jpg') for row in selected)
    for split in splits.glob('*_test.txt'):
        split.write_text('\n'.join(reversed(split.read_text().split())))
    assert actions.select_test_subset(tmp_path) == selected
    (splits / 'action_0_train.txt').write_text('action_0_002.jpg')
    with pytest.raises(ValueError, match='overlap'):
        actions.select_test_subset(tmp_path)


def test_comparison_rejects_different_inputs(experiments):
    comparison, _ = experiments
    with pytest.raises(ValueError, match='identical items'):
        comparison.compare({'metrics': {'item_count': 1}, 'items': [{'id': 'a'}]},
                           {'metrics': {'item_count': 1}, 'items': [{'id': 'b'}]}, {}, {})
