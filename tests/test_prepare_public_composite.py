from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tarfile
import zipfile

import pytest

spec = importlib.util.spec_from_file_location('prepare_public_composite', Path(__file__).parents[1] / 'scripts/prepare_public_composite.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def zip_file(path, members):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, content in members:
            archive.writestr(name, content)


@pytest.mark.parametrize('name', ['../escape.jpg', '/absolute.jpg', 'nested/../../bad', 'C:/bad', 'a\\b'])
def test_archive_rejects_unsafe_paths(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    zip_file(archive, [(name, b'a')])
    with pytest.raises(ValueError, match='Unsafe'):
        module.inventory(archive)


def test_archive_rejects_symlinks(tmp_path):
    archive = tmp_path / 'bad.tar.gz'
    with tarfile.open(archive, 'w:gz') as stream:
        member = tarfile.TarInfo('link')
        member.type = tarfile.SYMTYPE
        member.linkname = '/etc/passwd'
        stream.addfile(member)
    with pytest.raises(ValueError, match='link'):
        module.inventory(archive)


def test_duplicate_and_prefix_collision(tmp_path):
    archive = tmp_path / 'bad.zip'
    zip_file(archive, [('a', b'x'), ('a/b', b'y')])
    with pytest.raises(ValueError, match='collision'):
        module.inventory(archive)
    with pytest.warns(UserWarning):
        zip_file(archive, [('a', b'x'), ('a', b'y')])
    with pytest.raises(ValueError, match='Duplicate'):
        module.inventory(archive)


def make_albums(folder):
    folder.mkdir(parents=True)
    (folder / 'albums.jsonl').write_text(json.dumps({'album_id': 'a', 'metadata': {'image_root': '/private/creator'}, 'images': [{'image_id': '001'}]}) + '\n')
    (folder / 'splits.json').write_text(json.dumps({'train': ['a'], 'test': []}))
    (folder / 'tasks.jsonl').write_text(json.dumps({'task_id': 'task', 'album_id': 'a', 'image_ids': ['001'], 'task_type': 'intent_selection', 'prompt': 'choose a', 'target': {'selected_images': ['001']}}) + '\n')


def test_album_join_and_private_metadata_removed(tmp_path):
    make_albums(tmp_path / 'albums')
    tasks, counts = module.album_tasks(tmp_path / 'albums')
    assert counts['tasks'] == 1
    assert tasks[0]['supported'] is False
    assert '/private' not in json.dumps(tasks)
    assert tasks[0]['split'] == 'train'
    path = tmp_path / 'albums/tasks.jsonl'
    row = json.loads(path.read_text())
    row['target']['selected_images'] = ['missing']
    path.write_text(json.dumps(row) + '\n')
    with pytest.raises(ValueError, match='target join'):
        module.album_tasks(tmp_path / 'albums')


def make_corpus(root):
    downloads = root / 'downloads'
    downloads.mkdir()
    zip_file(downloads / 'koniq-images.zip', [('512x384/one.jpg', b'koniq')])
    zip_file(downloads / 'koniq-scores.zip', [('koniq10k_scores_and_distributions.csv', 'image_name,MOS\none.jpg,4.0\n')])
    zip_file(downloads / 'kadid.zip', [('kadid10k/images/I01.png', b'ref'), ('kadid10k/images/I01_01_01.png', b'kadid'), ('kadid10k/dmos.csv', 'dist_img,ref_img,dmos,var\nI01_01_01.png,I01.png,2.0,0.1\n')])
    for name, member_name in [('original', '100000.jpg'), ('strong', '100001.jpg')]:
        with tarfile.open(downloads / f'copydays-{name}.tar.gz', 'w:gz') as archive:
            data = b'gallery' if name == 'original' else b'query'
            member = tarfile.TarInfo(member_name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    make_albums(root / 'albumbench')


def test_prepare_native_targets_atomic_resume(tmp_path):
    make_corpus(tmp_path)
    output = tmp_path / 'manifest.json'
    result = module.prepare(tmp_path, output)
    assert result['schema_version'] == module.SCHEMA
    assert result['inventory']['tracks'] == {'koniq': 1, 'kadid': 1, 'copydays': 2}
    assert result['items'][1]['target'] == 2.0  # KADID's higher-is-better DMOS is not inverted.
    assert all((tmp_path / item['path']).is_file() for item in result['items'])
    assert not list(tmp_path.glob('.extract-*'))
    assert module.prepare(tmp_path, output) == result
    zip_file(tmp_path / 'downloads/koniq-images.zip', [('512x384/one.jpg', b'new')])
    with pytest.raises(ValueError, match='stale'):
        module.prepare(tmp_path, output)


def test_preflight_bounds_and_overlap_write_nothing(tmp_path, monkeypatch):
    make_corpus(tmp_path)
    with pytest.raises(ValueError, match='overlaps'):
        module.prepare(tmp_path, tmp_path / 'downloads/manifest.json')
    assert not (tmp_path / 'extracted').exists()
    monkeypatch.setattr(module, 'MAX_BYTES', 1)
    with pytest.raises(ValueError, match='bounds'):
        module.prepare(tmp_path, tmp_path / 'manifest.json')
    assert not (tmp_path / 'extracted').exists()


def test_missing_quality_labels_roll_back_stage(tmp_path):
    make_corpus(tmp_path)
    zip_file(tmp_path / 'downloads/koniq-scores.zip', [('koniq10k_scores_and_distributions.csv', 'image_name,MOS\nmissing.jpg,4.0\n')])
    with pytest.raises(ValueError, match='unmatched'):
        module.prepare(tmp_path, tmp_path / 'manifest.json')
    assert not (tmp_path / 'extracted').exists()
    assert not list(tmp_path.glob('.extract-*'))


def test_resume_rejects_altered_extracted_content(tmp_path):
    make_corpus(tmp_path)
    output = tmp_path / 'manifest.json'
    result = module.prepare(tmp_path, output)
    (tmp_path / result['items'][0]['path']).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='content is stale'):
        module.prepare(tmp_path, output)


def test_prepared_manifest_loads_in_runner(tmp_path):
    runner_spec = importlib.util.spec_from_file_location('composite_runner', Path(__file__).parents[1] / 'scripts/benchmark_public_composite.py')
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)
    make_corpus(tmp_path)
    path = tmp_path / 'manifest.json'
    result = module.prepare(tmp_path, path)
    assert runner.load_manifest(path, tmp_path) == result


def test_atomic_json_does_not_follow_predictable_temp_symlink(tmp_path):
    source = tmp_path / 'source.json'
    source.write_text('original')
    output = tmp_path / 'result.json'
    output.with_suffix('.json.tmp').symlink_to(source)
    module.atomic_json(output, {'valid': True})
    assert source.read_text() == 'original'
    assert json.loads(output.read_text()) == {'valid': True}


def test_download_directory_symlink_rejected_without_source_writes(tmp_path):
    root = tmp_path / 'root'
    root.mkdir()
    make_corpus(root)
    downloads = root / 'downloads'
    outside = tmp_path / 'outside'
    downloads.rename(outside)
    downloads.symlink_to(outside, target_is_directory=True)
    source = outside / 'koniq-images.zip'
    before = source.read_bytes()
    with pytest.raises(ValueError, match='symlinks'):
        module.prepare(root, downloads / 'koniq-images.zip')
    assert source.read_bytes() == before
    assert not (root / 'extracted').exists()


def test_compressed_bound_precedes_extraction(tmp_path, monkeypatch):
    make_corpus(tmp_path)
    monkeypatch.setattr(module, 'MAX_COMPRESSED_BYTES', 1)
    with pytest.raises(ValueError, match='compressed'):
        module.prepare(tmp_path, tmp_path / 'manifest.json')
    assert not (tmp_path / 'extracted').exists()


def test_native_repeated_album_ratings_are_preserved_and_flagged(tmp_path):
    folder = tmp_path / 'albums'
    make_albums(folder)
    path = folder / 'tasks.jsonl'
    row = json.loads(path.read_text())
    row['task_type'] = 'intent_rating'
    row['target'] = {'images': ['001', '001'], 'ratings': [1, 3]}
    path.write_text(json.dumps(row) + '\n')
    tasks, inventory = module.album_tasks(folder)
    assert tasks[0]['target'] == row['target']
    assert tasks[0]['source_target_duplicate_ids'] == 1
    assert inventory['tasks_with_duplicate_target_ids'] == 1


def test_archive_entry_budget_enforced_during_inventory(tmp_path, monkeypatch):
    archive = tmp_path / 'many.zip'
    zip_file(archive, [('one', b'1'), ('two', b'2')])
    monkeypatch.setattr(module, 'MAX_ENTRIES', 1)
    with pytest.raises(ValueError, match='entry or byte bounds'):
        module.inventory(archive)


def test_koniq_release_extras_retained_without_fabricated_targets(tmp_path):
    make_corpus(tmp_path)
    zip_file(tmp_path / 'downloads/koniq-images.zip', [('512x384/one.jpg', b'koniq'), ('512x384/extra.jpg', b'unlabelled')])
    result = module.prepare(tmp_path, tmp_path / 'manifest.json')
    koniq = [i for i in result['items'] if i['track'] == 'koniq']
    assert len(koniq) == 1
    assert koniq[0]['id'] == 'koniq:one.jpg'
    assert result['inventory']['unlabelled_counts']['koniq'] == 1
    assert result['inventory']['raw_image_files'] == 6
    assert result['release_anomalies']['koniq_images_without_scores'][0]['id'] == 'koniq:extra.jpg'
    assert (tmp_path / 'extracted/koniq-images/512x384/extra.jpg').read_bytes() == b'unlabelled'


def test_kadid_validated_appledouble_metadata_is_not_a_photo(tmp_path):
    folder = tmp_path / 'images'
    folder.mkdir()
    (folder / 'I01.png').write_bytes(b'image')
    (folder / '._I01.png').write_bytes(b'\x00\x05\x16\x07' + bytes(4092))
    assert set(module.unique_files(folder, ('.png',))) == {'I01.png'}
    # A dot-prefixed actual photo must not be silently excluded as metadata.
    (folder / '._I02.png').write_bytes(b'\x89PNG\r\n\x1a\nreal')
    assert set(module.unique_files(folder, ('.png',))) == {'I01.png', '._I02.png'}


def test_kadid_ordinary_extra_remains_strict(tmp_path):
    make_corpus(tmp_path)
    zip_file(tmp_path / 'downloads/kadid.zip', [('kadid10k/images/I01.png', b'ref'), ('kadid10k/images/I01_01_01.png', b'kadid'), ('kadid10k/images/extra.png', b'ordinary'), ('kadid10k/dmos.csv', 'dist_img,ref_img,dmos,var\nI01_01_01.png,I01.png,2.0,0.1\n')])
    with pytest.raises(ValueError, match='kadid unlabelled'):
        module.prepare(tmp_path, tmp_path / 'manifest.json')
