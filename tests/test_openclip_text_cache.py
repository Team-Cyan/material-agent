"""Real tensor compatibility checks without model downloads or filesystem images."""
from concurrent.futures import ThreadPoolExecutor
import sys
from types import SimpleNamespace

import pytest
from PIL import Image

from material_agent.adapters.models.openclip_semantic import _OpenClipRuntime


@pytest.fixture
def runtime(monkeypatch):
    torch = pytest.importorskip('torch')

    class Model:
        def __init__(self):
            self.text_calls = 0
            self.fail = False

        def eval(self):
            return self

        def encode_image(self, image):
            return image

        def encode_text(self, text):
            self.text_calls += 1
            if self.fail:
                raise RuntimeError('encoding failed')
            return text

    model = Model()
    vectors = {'a': [1., 0.], 'b': [0., 1.], 'c': [1., 1.]}
    monkeypatch.setitem(sys.modules, 'open_clip', SimpleNamespace(
        create_model_and_transforms=lambda *a, **k: (
            model, None, lambda image: torch.tensor([1., 0.])),
        get_tokenizer=lambda name: lambda prompts: torch.tensor([vectors[p] for p in prompts]),
    ))
    return _OpenClipRuntime(model_name='fixture', pretrained='fixture', device='cpu', cache_dir=None)


def test_text_cache_reuses_bank_and_preserves_order(runtime):
    image = Image.new('RGB', (2, 2))
    first = runtime.classify(image, ['a', 'b'])
    assert runtime.classify(image, ['a', 'b']) == first
    assert runtime.model.text_calls == 1
    assert runtime.classify(image, ['b', 'a']) == list(reversed(first))
    assert runtime.model.text_calls == 2
    runtime.classify(image, ['a', 'b'])
    assert runtime.model.text_calls == 3  # Only the last bank is retained.


def test_text_cache_does_not_publish_failed_encoding(runtime):
    runtime.model.fail = True
    with pytest.raises(RuntimeError, match='encoding failed'):
        runtime.classify(Image.new('RGB', (2, 2)), ['a', 'b'])
    runtime.model.fail = False
    result = runtime.classify(Image.new('RGB', (2, 2)), ['a', 'b'])
    assert result[0] > result[1]
    assert runtime.model.text_calls == 2


def test_text_cache_is_bounded_and_invalidates_replaced_model(runtime):
    image = Image.new('RGB', (2, 2))
    runtime.classify(image, ['a'] * 257)
    runtime.classify(image, ['a'] * 257)
    assert runtime.model.text_calls == 2
    runtime.classify(image, ['a', 'b'])
    runtime.model = type(runtime.model)()
    runtime.classify(image, ['a', 'b'])
    assert runtime.model.text_calls == 1


def test_text_cache_serializes_concurrent_calls(runtime):
    image = Image.new('RGB', (2, 2))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: runtime.classify(image, ['a', 'b']), range(8)))
    assert all(row == results[0] for row in results)
    assert runtime.model.text_calls == 1
