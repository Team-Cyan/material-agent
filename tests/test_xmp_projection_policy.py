"""D03 compatibility fixtures in memory; no XMP or source media is written."""
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from material_agent.adapters.metadata import exiftool_xmp as xmp


def root(rating=None, *, attribute=False):
    value = '' if rating is None else (
        f'xmp:Rating="{rating}"' if attribute else f'<xmp:Rating>{rating}</xmp:Rating>')
    return ET.fromstring(
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        f'<rdf:Description {value if attribute else ""}>{"" if attribute else value}'
        '</rdf:Description></rdf:RDF>')


@pytest.mark.parametrize('rating,allowed', [(None, True), ('0', True), ('0.0', True),
    ('1', False), ('2', False), ('3', False), ('4', False), ('5', False), ('-1', False), ('6', False)])
@pytest.mark.parametrize('attribute', [False, True])
def test_rating_projection_preserves_every_nonzero(rating, allowed, attribute):
    assert xmp._rating_write_allowed(root(rating, attribute=attribute)) is allowed


@pytest.mark.parametrize('rating', ['', ' ', 'unknown', 'NaN', 'Infinity', '1.5'])
def test_malformed_rating_fails_closed(rating):
    with pytest.raises(ValueError, match='Malformed'):
        xmp._rating_write_allowed(root(rating))


def test_duplicate_rating_fails_closed():
    tree = root('0')
    tree[0].set(f"{{{xmp._XMP_NS['xmp']}}}Rating", '5')
    with pytest.raises(ValueError, match='duplicate'):
        xmp._rating_write_allowed(tree)


@pytest.mark.parametrize('decision,keyword', [('keep','keep'), ('review','keep'), ('reject','reject')])
def test_keywords_replace_only_two_exact_owned_values(decision, keyword):
    assert xmp._project_selection_keywords(
        ['family', 'material-agent:keep', 'material-agent:reject', 'material-agent:keep-personal'],
        [f'pj:decision={decision}'],
    ) == ['family', 'material-agent:keep-personal', f'material-agent:{keyword}']


@pytest.mark.parametrize('rating,write_rating', [(None, True), ('0', True), ('5', False), ('-1', False)])
def test_update_command_preserves_nonzero_and_refreshes_keywords(monkeypatch, rating, write_rating):
    writer = xmp.ExifToolXMPWriter()
    monkeypatch.setattr(xmp, '_read_xmp_root', lambda path: root(rating))
    monkeypatch.setattr(writer, '_read_non_pj_subject_tags', lambda path: ['family', 'material-agent:reject'])
    monkeypatch.setattr(writer, '_read_non_pj_identifier_tags', lambda path: ['foreign-id'])
    monkeypatch.setattr(writer, '_read_non_pj_hierarchical_subject_tags', lambda path: ['People|Family'])
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(xmp.subprocess, 'run', run)
    record = writer._update_existing_xmp('never-written.xmp', rating=2,
        subject_tags=['pj:decision=keep'], instructions='', description='')
    command = run.call_args.args[0]
    assert ('-XMP-xmp:Rating=2' in command) is write_rating
    assert '-XMP-dc:Subject=family' in command
    assert '-XMP-dc:Subject=material-agent:keep' in command
    assert '-XMP-dc:Subject=material-agent:reject' not in command
    assert '-XMP-xmp:Identifier=foreign-id' in command
    assert record['rating'] == ('written' if write_rating else 'preserved_nonzero')
    assert record['effective_rating'] == (2 if write_rating else rating)


def test_new_packet_has_visible_selection_and_separate_machine_provenance():
    class MemoryPacket:
        content = ''
        def write_text(self, value, **kwargs):
            self.content = value
    packet = MemoryPacket()
    xmp.ExifToolXMPWriter()._write_minimal_xmp_content(packet, 2, ['family'],
        ['pj:score=3.0', 'pj:decision=review'], [], '', '')
    tree = ET.fromstring(packet.content)
    assert [item.text for item in tree.findall('.//dc:subject/rdf:Bag/rdf:li', xmp._XMP_NS)] == ['family', 'material-agent:keep']
    assert tree.find('.//xmp:Rating', xmp._XMP_NS).text == '2'


def test_preserved_external_rating_is_not_recorded_as_ai_owned(monkeypatch):
    from material_agent.app import review_runtime
    from material_agent.utils.config_validator import normalize_config
    writer = xmp.ExifToolXMPWriter()
    record = {'rating': 'preserved_nonzero', 'requested_rating': 2, 'effective_rating': '5', 'keywords': 'written'}
    monkeypatch.setattr(writer, 'write', lambda *a, **kw: record)
    monkeypatch.setattr(review_runtime, 'ExifToolXMPWriter', lambda config: writer)
    monkeypatch.setattr(review_runtime, 'make_client', lambda config: object())
    monkeypatch.setattr(review_runtime, 'make_fast_screening_port', lambda config: None)
    state = Mock()
    executor = review_runtime.build_review_job_executor(repository=Mock(), config=normalize_config({}),
        state=state, progress=Mock(), dry_run=False)
    payload = {'score_total': 4., 'scores': {}, 'meta': {}, 'decision': 'keep'}
    executor.review_job.write_file('never-written.ARW', payload, rank=1, group_id='g', group_size=1)
    saved = state.mark_done.call_args.kwargs
    assert 'rating' not in saved['xmp_payload']
    assert saved['metadata']['xmp_projection'] == record
    assert saved['star_rating'] == 2  # AI proposal remains separate from external 5 stars.


def test_generated_packet_exiftool_readback_via_stdin():
    import json
    import shutil
    import subprocess
    if shutil.which('exiftool') is None:
        pytest.skip('ExifTool unavailable')

    class MemoryPacket:
        def write_text(self, value, **kwargs):
            self.content = value

    packet = MemoryPacket()
    xmp.ExifToolXMPWriter()._write_minimal_xmp_content(
        packet, 3, ['family'], ['pj:decision=keep'], [], '', '')
    # No output filename or assignment flags: ExifTool only reads the pipe.
    result = subprocess.run(['exiftool', '-j', '-Rating', '-Subject', '-Identifier', '-'],
                            input=packet.content.encode(), capture_output=True, check=True)
    metadata = json.loads(result.stdout)[0]
    assert metadata['Rating'] == 3
    assert metadata['Subject'] == ['family', 'material-agent:keep']
    assert metadata['Identifier'] == 'pj:decision=keep'


def test_conflicting_selection_decisions_fail_before_projection():
    with pytest.raises(ValueError, match='ambiguous'):
        xmp._project_selection_keywords(['family'], ['pj:decision=keep', 'pj:decision=reject'])
