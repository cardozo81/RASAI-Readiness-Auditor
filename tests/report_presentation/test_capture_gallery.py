"""Visual capture embedded in the independent offline presentation."""
import base64
import hashlib
import json
from pathlib import Path
import sqlite3

from rasai.catalog_report_site import _sqlite_logical_digest
from rasai.parallel_report.artifact_reader import inventory
from rasai.parallel_report.capture_gallery import package_captures
from rasai.parallel_report.generator import generate
from rasai.parallel_report.publication import compatible_manifest

from test_parallel_report import fixture

# A standard, valid, 1x1 raster (no user data, no external acquisition).
TINY_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC'
    'AAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII='
)


def _audit_with_screenshot(tmp_path):
    root = fixture(tmp_path / 'audit')
    original = root / 'artifacts' / 'visual' / 'capture.png'
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(TINY_PNG)
    with sqlite3.connect(root / 'audit.db') as db:
        db.execute('ALTER TABLE page_snapshots ADD COLUMN device TEXT')
        db.execute('ALTER TABLE page_snapshots ADD COLUMN captured_at TEXT')
        db.execute('ALTER TABLE page_snapshots ADD COLUMN final_url TEXT')
        db.execute('ALTER TABLE page_snapshots ADD COLUMN browser_metadata TEXT')
        db.execute('UPDATE page_snapshots SET device=?, captured_at=?, final_url=?, browser_metadata=?',
                   ('MOBILE', '2026-11-16T12:00:00Z', 'https://example.test',
                    json.dumps({'visual_artifact_ref': 'artifacts/visual/capture.png',
                                'browser_identity': {'channel': 'Chromium'}})))
    return root, original


def test_screenshot_is_visible_inline_offline_and_manifest_verified(tmp_path):
    root, original = _audit_with_screenshot(tmp_path)
    source_hash = hashlib.sha256((root / 'audit.db').read_bytes()).hexdigest()
    visual_hash = hashlib.sha256(TINY_PNG).hexdigest()
    output = generate(root)
    html = (output / 'extracao.html').read_text(encoding='utf-8')
    manifest = json.loads((output / '_geracao.json').read_text(encoding='utf-8'))
    paths = [p for p in (output / 'assets' / 'capturas').glob('*')]
    assert len(paths) == 1
    assert paths[0].read_bytes() == original.read_bytes() == TINY_PNG
    assert paths[0].name == visual_hash + '.png'
    assert manifest['visual_previews'][0]['status'] == 'AVAILABLE'
    assert manifest['visual_previews'][0]['sha256'] == visual_hash
    assert manifest['sha256_per_file']['assets/capturas/' + paths[0].name] == visual_hash
    # shell() adds navigation anchor identifiers to every <h2>.
    assert 'Prévia visual das páginas capturadas</h2>' in html
    assert '<img class="capture-image-preview" src="assets/capturas/' in html
    assert 'data-modal="capture-image-0"' in html
    assert 'dialog class="detail-dialog capture-image-dialog"' in html
    assert '16/11/2026 09:00:00 (America/Sao_Paulo)' in html or '2026-11-16T12:00:00Z' in html
    assert '../report-catalog/' not in html
    assert hashlib.sha256((root / 'audit.db').read_bytes()).hexdigest() == source_hash
    assert compatible_manifest(output, inventory(root), _sqlite_logical_digest(root / 'audit.db'))
    paths[0].unlink()
    assert compatible_manifest(output, inventory(root), _sqlite_logical_digest(root / 'audit.db')) is None


def test_missing_invalid_or_traversal_screenshot_never_appears_as_image(tmp_path):
    root = tmp_path / 'audit'
    root.mkdir()
    (root / 'fake.png').write_bytes(b'Not a PNG')
    (root / 'outside.svg').write_bytes(b'<svg onload="alert(1)"></svg>')
    stage = tmp_path / 'stage'
    stage.mkdir()
    rows = [
        {'browser_metadata': {'visual_artifact_ref': '../outside.png'}},
        {'browser_metadata': {'visual_artifact_ref': 'fake.png'}},
        {'browser_metadata': {'visual_artifact_ref': 'outside.svg'}},
        {'browser_metadata': {'visual_artifact_ref': 'missing.png'}},
        {'browser_metadata': {'visual_artifact_ref': 'https://example.test/a.png'}},
    ]
    output = package_captures(root, rows, stage, inventory(root))
    assert len(output) == len(rows)
    assert all(p['status'] == 'UNAVAILABLE' and p['local_path'] is None for p in output)
    assert not list(stage.rglob('*.png'))


def test_two_device_screenshots_remain_independent_without_duplicate_binary(tmp_path):
    root, original = _audit_with_screenshot(tmp_path)
    with sqlite3.connect(root / 'audit.db') as db:
        db.execute('INSERT INTO page_snapshots(snapshot_id,rendered_artifact_ref,device,'
                   'captured_at,final_url,browser_metadata) VALUES(?,?,?,?,?,?)',
                   ('snapshot-2', 'artifacts/page.html', 'DESKTOP',
                    '2026-11-16T12:30:00Z', 'https://example.test',
                    json.dumps({'visual_artifact_ref': 'artifacts/visual/capture.png'})))
    output = generate(root)
    html = (output / 'extracao.html').read_text(encoding='utf-8')
    manifest = json.loads((output / '_geracao.json').read_text(encoding='utf-8'))
    assert len(manifest['visual_previews']) == 2
    assert all(item['status'] == 'AVAILABLE' for item in manifest['visual_previews'])
    assert len(list((output / 'assets' / 'capturas').glob('*.png'))) == 1
    assert html.count('class="capture-image-preview"') == 2
    assert 'Captura 1 - Móvel' in html
    assert 'Captura 2 - Desktop' in html
