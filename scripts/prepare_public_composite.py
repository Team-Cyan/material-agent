#!/usr/bin/env python3
"""Prepare an isolated public diagnostic corpus; never infer safe-cover labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
import zipfile
from collections import Counter, defaultdict

SCHEMA = 'material-agent.public-composite.v1'
ARCHIVES = {'koniq-images.zip': 'koniq-images', 'koniq-scores.zip': 'koniq-scores',
            'kadid.zip': 'kadid', 'copydays-original.tar.gz': 'copydays-original',
            'copydays-strong.tar.gz': 'copydays-strong'}
MAX_BYTES = 15_000_000_000
MAX_ENTRIES = 60000
MAX_COMPRESSED_BYTES = 8_000_000_000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name: str) -> str:
    path = PurePosixPath(name)
    if not name or '\\' in name or path.is_absolute() or '..' in path.parts or ':' in path.parts[0]:
        raise ValueError(f'Unsafe archive member: {name!r}')
    normalized = str(path)
    if normalized == '.':
        raise ValueError('Empty archive member')
    return normalized


def inventory(path: Path) -> list[tuple[str, int, bool]]:
    result = []
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                    raise ValueError('Archive contains a special file')
                if member.flag_bits & 1:
                    raise ValueError('Encrypted archive is unsupported')
                if len(result) >= MAX_ENTRIES or member.file_size > MAX_BYTES:
                    raise ValueError('Archive exceeds entry or byte bounds')
                result.append((safe_name(member.filename), member.file_size, member.is_dir()))
    else:
        with tarfile.open(path, 'r:*') as archive:
            for member in archive:
                if not member.isfile() and not member.isdir():
                    raise ValueError('Archive contains a link or special file')
                if len(result) >= MAX_ENTRIES or member.size > MAX_BYTES:
                    raise ValueError('Archive exceeds entry or byte bounds')
                result.append((safe_name(member.name), member.size, member.isdir()))
    seen = set()
    for name, size, _ in result:
        if name in seen or size < 0:
            raise ValueError('Duplicate archive member or negative size')
        seen.add(name)
    files = {name for name, _, directory in result if not directory}
    for name in seen:
        if any(str(parent) in files for parent in PurePosixPath(name).parents):
            raise ValueError('Archive file/directory collision')
    return result


def extract(path: Path, destination: Path, members: list[tuple[str, int, bool]]) -> None:
    """Manually extract only preflighted ordinary members with exact byte bounds."""
    is_zip = zipfile.is_zipfile(path)
    archive = zipfile.ZipFile(path) if is_zip else tarfile.open(path, 'r:*')
    with archive:
        sources = archive.infolist() if is_zip else archive.getmembers()
        for source, (name, size, directory) in zip(sources, members, strict=True):
            output = destination / name
            if directory:
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.open(source) if is_zip else archive.extractfile(source)
            if stream is None:
                raise ValueError('Missing archive stream')
            with stream, output.open('xb') as target:
                remaining = size
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('Truncated archive member')
                    target.write(chunk)
                    remaining -= len(chunk)
                if stream.read(1):
                    raise ValueError('Archive member exceeds declared size')


def unique_files(directory: Path, suffixes: tuple[str, ...]) -> dict[str, Path]:
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.suffix.lower() in suffixes and '__MACOSX' not in path.parts:
            # Native releases sometimes place AppleDouble resource forks beside images.
            # Exclude only verified metadata; ordinary extra images remain strict.
            if path.name.startswith('._'):
                with path.open('rb') as stream:
                    if stream.read(4) == b'\x00\x05\x16\x07':
                        continue
            if path.name in result:
                raise ValueError(f'Duplicate image basename: {path.name}')
            result[path.name] = path
    return result


def quality_items(root: Path, extracted: Path, track: str) -> list[dict]:
    folder = extracted / ('koniq-images' if track == 'koniq' else 'kadid')
    images = unique_files(folder, ('.jpg', '.jpeg', '.png'))
    csv_folder = extracted / ('koniq-scores' if track == 'koniq' else 'kadid')
    csv_name = 'koniq10k_scores_and_distributions.csv' if track == 'koniq' else 'dmos.csv'
    candidates = list(csv_folder.rglob(csv_name))
    if len(candidates) != 1:
        raise ValueError(f'Expected one {csv_name}')
    items, seen, references = [], set(), set()
    with candidates[0].open(newline='', encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            name = row['image_name' if track == 'koniq' else 'dist_img']
            if name != Path(name).name or name in seen or name not in images:
                raise ValueError(f'Invalid/duplicate/unmatched {track} image label')
            seen.add(name)
            target = float(row['MOS' if track == 'koniq' else 'dmos'])
            if not math.isfinite(target) or not 1 <= target <= 5:
                raise ValueError('Quality target must be finite')
            item = {'id': f'{track}:{name}', 'path': str(images[name].relative_to(root)),
                    'track': track, 'target': target}
            if track == 'kadid':
                match = re.fullmatch(r'I(\d+)_(\d+)_(\d+)\.png', name)
                if match is None or row['ref_img'] not in images:
                    raise ValueError('Invalid KADID distortion identity/reference')
                references.add(row['ref_img'])
                item.update(group=row['ref_img'], distortion=int(match[2]), level=int(match[3]))
            items.append(item)
    if track == 'kadid' and set(images) != seen | references:
        raise ValueError(f'{track} unlabelled image files')
    return items


def copy_items(root: Path, extracted: Path) -> list[dict]:
    originals = unique_files(extracted / 'copydays-original', ('.jpg', '.jpeg', '.png'))
    queries = unique_files(extracted / 'copydays-strong', ('.jpg', '.jpeg', '.png'))
    groups, items = {}, []
    for name, path in originals.items():
        if not re.fullmatch(r'\d{6}\.jpg', name) or name[4:6] != '00' or name[:4] in groups:
            raise ValueError('Invalid Copydays gallery identity')
        groups[name[:4]] = name
        items.append({'id': f'copydays:gallery:{name}', 'path': str(path.relative_to(root)),
                      'track': 'copydays', 'role': 'gallery', 'source_id': name[:4]})
    for name, path in queries.items():
        if not re.fullmatch(r'\d{6}\.jpg', name) or name[:4] not in groups:
            raise ValueError('Unmatched Copydays query identity')
        items.append({'id': f'copydays:query:{name}', 'path': str(path.relative_to(root)),
                      'track': 'copydays', 'role': 'query', 'source_id': name[:4]})
    if not originals or not queries:
        raise ValueError('Copydays gallery/query must be nonempty')
    return items


def album_tasks(directory: Path) -> tuple[list[dict], dict]:
    albums = {}
    with (directory / 'albums.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            album_id = row['album_id']
            ids = [image['image_id'] for image in row['images']]
            if album_id in albums or len(set(ids)) != len(ids):
                raise ValueError('Duplicate AlbumBench album/image identity')
            albums[album_id] = set(ids)
    splits = json.loads((directory / 'splits.json').read_text())
    membership = {}
    for split, ids in splits.items():
        for album_id in ids:
            if album_id in membership or album_id not in albums:
                raise ValueError('Invalid AlbumBench split membership')
            membership[album_id] = split
    if set(membership) != set(albums):
        raise ValueError('AlbumBench split does not cover inventory')
    tasks, seen = [], set()
    with (directory / 'tasks.jsonl').open() as stream:
        for line in stream:
            row = json.loads(line)
            album_id, task_id = row['album_id'], row['task_id']
            ids = row['image_ids']
            if task_id in seen or album_id not in albums or set(ids) != albums[album_id] or len(set(ids)) != len(ids):
                raise ValueError('Invalid AlbumBench task identity/inventory join')
            seen.add(task_id)
            target = row['target']
            kind = row['task_type']
            if kind == 'intent_selection':
                referenced = target['selected_images']
            elif kind == 'intent_rating':
                referenced = target['images']
                ratings = target['ratings']
                if len(referenced) != len(ratings) or any(type(r) not in (int, float) or not math.isfinite(r) or not 0 <= r <= 3 for r in ratings):
                    raise ValueError('Invalid AlbumBench ratings')
            elif kind == 'group_labeling':
                referenced = [image for group in target['groups'] for image in group['images']]
                if target['total_groups'] != len(target['groups']):
                    raise ValueError('Invalid AlbumBench group count')
            else:
                raise ValueError('Unknown AlbumBench task type')
            if not set(referenced) <= set(ids) or (kind != 'intent_rating' and len(set(referenced)) != len(referenced)):
                raise ValueError('Invalid AlbumBench target join')
            tasks.append({'id': task_id, 'task_type': kind, 'album_id': album_id,
                          'prompt': row['prompt'], 'image_ids': ids, 'target': target,
                          'split': membership[album_id], 'supported': False,
                          'status': 'images_unavailable',
                          'source_target_duplicate_ids': len(referenced) - len(set(referenced))})
    return tasks, {'albums': len(albums), 'images': sum(map(len, albums.values())),
                   'tasks': len(tasks), 'task_types': dict(Counter(t['task_type'] for t in tasks)),
                   'splits': dict(Counter(membership.values())),
                   'tasks_with_duplicate_target_ids': sum(t['source_target_duplicate_ids'] > 0 for t in tasks)}


def atomic_json(path: Path, payload: dict) -> None:
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(root: Path, output: Path, checkpoint: Path | None = None) -> dict:
    root, output = root.resolve(), output.resolve()
    extracted = root / 'extracted'
    downloads = root / 'downloads'
    inputs = [downloads / name for name in ARCHIVES]
    metadata = root / 'albumbench'
    if extracted.is_symlink() or output.is_dir() or output == root or output.is_relative_to(extracted) or output.is_relative_to(downloads) or output.is_relative_to(metadata):
        raise ValueError('Manifest overlaps input/extraction directories')
    if any(folder.is_symlink() for folder in (downloads, metadata, extracted)) or any(path.is_symlink() for folder in (downloads, metadata, extracted) if folder.exists() for path in folder.rglob('*')):
        raise ValueError('Input and extraction symlinks are not allowed')
    if any(not path.is_file() for path in inputs):
        raise ValueError('All complete archives are required; .part files are not accepted')
    if checkpoint and (checkpoint.is_dir() or checkpoint.resolve().is_relative_to(downloads) or checkpoint.resolve().is_relative_to(extracted) or checkpoint.resolve().is_relative_to(metadata) or checkpoint.resolve() == output):
        raise ValueError('Checkpoint overlaps inputs or output')
    if sum(path.stat().st_size for path in inputs) > MAX_COMPRESSED_BYTES:
        raise ValueError('Corpus exceeds compressed byte bounds')
    inventories = {path.name: inventory(path) for path in inputs}
    byte_count = sum(size for members in inventories.values() for _, size, _ in members)
    entries = sum(map(len, inventories.values()))
    if byte_count > MAX_BYTES or entries > MAX_ENTRIES:
        raise ValueError('Corpus exceeds extraction bounds')
    receipts = [{'archive': p.name, 'sha256': sha256(p), 'bytes': p.stat().st_size,
                 'expanded_bytes': sum(size for _, size, _ in inventories[p.name]),
                 'entries': len(inventories[p.name])} for p in inputs]
    fingerprint = hashlib.sha256(json.dumps(receipts, sort_keys=True).encode()).hexdigest()
    metadata_receipts = [{'file': name, 'sha256': sha256(metadata / name)} for name in ('albums.jsonl', 'tasks.jsonl', 'splits.json')]
    tasks, album_inventory = album_tasks(metadata)
    if checkpoint:
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(checkpoint, {'state': 'preflight_passed', 'archive_fingerprint': fingerprint, 'receipts': receipts})
    reuse = extracted.exists()
    if reuse:
        stamp = extracted / 'extraction.json'
        if not stamp.is_file() or json.loads(stamp.read_text()).get('archive_fingerprint') != fingerprint:
            raise ValueError('Existing extraction fingerprint is stale')
        expected_hashes = json.loads(stamp.read_text()).get('file_hashes')
        if not isinstance(expected_hashes, dict):
            raise ValueError('Existing extraction integrity stamp is missing')
        actual_files = {str(p.relative_to(extracted)): p for p in extracted.rglob('*') if p.is_file() and p != stamp}
        if set(actual_files) != set(expected_hashes) or any(p.is_symlink() or sha256(p) != expected_hashes[name] for name, p in actual_files.items()):
            raise ValueError('Existing extraction content is stale')
        workspace = extracted
    else:
        workspace = Path(tempfile.mkdtemp(prefix='.extract-', dir=root))
    try:
        if not reuse:
            for path in inputs:
                extract(path, workspace / ARCHIVES[path.name], inventories[path.name])
            if any(sha256(path) != receipt['sha256'] for path, receipt in zip(inputs, receipts, strict=True)):
                raise ValueError('Archive changed during extraction')
            file_hashes = {str(p.relative_to(workspace)): sha256(p) for p in workspace.rglob('*') if p.is_file()}
            atomic_json(workspace / 'extraction.json', {'archive_fingerprint': fingerprint, 'file_hashes': file_hashes})
        items = quality_items(root, workspace, 'koniq') + quality_items(root, workspace, 'kadid') + copy_items(root, workspace)
        # Paths are rewritten before the atomically staged extraction is installed.
        for item in items:
            if not reuse:
                item['path'] = str(Path('extracted') / Path(item['path']).relative_to(workspace.name))
        hashes = defaultdict(list)
        for item in items:
            path = root / item['path'] if reuse else workspace / Path(item['path']).relative_to('extracted')
            digest = sha256(path)
            item['sha256'] = digest
            hashes[digest].append(item)
        labelled_koniq = {Path(i['path']).name for i in items if i['track'] == 'koniq'}
        unlabelled_koniq = [{'id': f'koniq:{name}', 'sha256': sha256(path)} for name, path in unique_files(workspace / 'koniq-images', ('.jpg', '.jpeg', '.png')).items() if name not in labelled_koniq]
        for record in unlabelled_koniq:
            hashes[record['sha256']].append({'id': record['id'], 'track': 'koniq'})
        kadid_files = unique_files(workspace / 'kadid', ('.jpg', '.jpeg', '.png'))
        for reference in sorted({i['group'] for i in items if i['track'] == 'kadid'}):
            digest = sha256(kadid_files[reference])
            hashes[digest].append({'id': f'kadid:reference:{reference}', 'track': 'kadid'})
        duplicates = [{'sha256': digest, 'ids': [i['id'] for i in group]} for digest, group in hashes.items() if len({i['track'] for i in group}) > 1]
        payload = {'schema_version': SCHEMA, 'items': items, 'album_tasks': tasks,
                   'inventory': {'items': len(items), 'tracks': dict(Counter(i['track'] for i in items)), 'albumbench': album_inventory, 'unlabelled_counts': {'koniq': len(unlabelled_koniq)}, 'raw_image_files': len(items) + len(unlabelled_koniq) + len({i['group'] for i in items if i['track'] == 'kadid'})},
                   'receipts': receipts, 'metadata_receipts': metadata_receipts, 'archive_fingerprint': fingerprint,
                   'cross_dataset_byte_duplicates': duplicates,
                   'release_anomalies': {'koniq_images_without_scores': unlabelled_koniq},
                   'limits': {'expanded_bytes': MAX_BYTES, 'archive_entries': MAX_ENTRIES, 'compressed_bytes': MAX_COMPRESSED_BYTES},
                   'kadid_inventory': {'reference_families': len({i['group'] for i in items if i['track'] == 'kadid'}), 'distortions': len({i['distortion'] for i in items if i['track'] == 'kadid'}), 'levels': len({i['level'] for i in items if i['track'] == 'kadid'})},
                   'label_contract': 'Native quality and copy labels only; no safe-cover witnesses.',
                   'albumbench_revision': '20c3e1e5841398f702df77aaf28c08b5b327c5e7'}
        if not reuse:
            os.replace(workspace, extracted)
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(output, payload)
        if checkpoint:
            atomic_json(checkpoint, {'state': 'prepared', 'archive_fingerprint': fingerprint, 'manifest_sha256': sha256(output), 'inventory': payload['inventory']})
        return payload
    finally:
        if not reuse and workspace.exists():
            shutil.rmtree(workspace)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    args = parser.parse_args()
    result = prepare(args.root, args.output or args.root / 'manifest.json', args.checkpoint)
    print(json.dumps(result['inventory'], sort_keys=True))


if __name__ == '__main__':
    main()
