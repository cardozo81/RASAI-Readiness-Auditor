"""Read-only packaging of already persisted browser screenshots.

Captures are independent of report-catalog. Never fetch, render, regenerate,
decode HTML, or change audit evidence. Only confined raster files are accepted.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import shutil

from .artifact_reader import confined, digest

MAX_CAPTURES = 32
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 80 * 1024 * 1024
_EXTENSIONS = {'.png': '.png', '.jpg': '.jpg', '.jpeg': '.jpg', '.webp': '.webp'}
_LOCAL_PATTERN = re.compile(r'^assets/capturas/[0-9a-f]{64}\.(?:png|jpg|webp)$')


def _metadata(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _valid_raster(source, extension):
    with source.open('rb') as stream:
        header = stream.read(16)
    if extension == '.png':
        return header.startswith(b'\x89PNG\r\n\x1a\n')
    if extension == '.jpg':
        return header.startswith(b'\xff\xd8\xff')
    if extension == '.webp':
        return header.startswith(b'RIFF') and header[8:12] == b'WEBP'
    return False


def package_captures(root, snapshots, stage, source_inventory):
    """Return positional visual projection, copy verified local rasters only.

    Hashes must match the initial full audit inventory both before and after
    copying. Unavailable/unsafe captures remain explicit N/D in presentation.
    """
    previews = []
    copied = set()
    total = 0
    for index, snapshot in enumerate(snapshots):
        meta = _metadata(snapshot.get('browser_metadata'))
        reference = meta.get('visual_artifact_ref')
        item = {'row_index': index, 'status': 'UNAVAILABLE',
                'local_path': None, 'sha256': None, 'size_bytes': None,
                'reason': 'Nenhuma imagem da captura foi persistida.'}
        if not isinstance(reference, str) or not reference.strip():
            previews.append(item)
            continue
        item['reason'] = 'Imagem não disponível ou incompatível com a exportação segura.'
        if index >= MAX_CAPTURES:
            item['reason'] = 'Limite de capturas visuais por apresentação atingido.'
            previews.append(item)
            continue
        try:
            path = confined(root, reference)
            extension = _EXTENSIONS.get(path.suffix.casefold())
            if not extension or not path.is_file():
                previews.append(item)
                continue
            size = path.stat().st_size
            if not 0 < size <= MAX_IMAGE_BYTES:
                item['reason'] = 'Imagem fora do limite de tamanho admitido.'
                previews.append(item)
                continue
            expected = source_inventory.get(path.relative_to(root).as_posix())
            if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
                previews.append(item)
                continue
            persisted = meta.get('visual_artifact_sha256')
            if persisted is not None and isinstance(persisted, str) and re.fullmatch(r'[0-9a-fA-F]{64}', persisted):
                if persisted.casefold() != expected:
                    item['reason'] = 'Integridade da captura visual divergente.'
                    previews.append(item)
                    continue
            if not _valid_raster(path, extension):
                item['reason'] = 'Arquivo sem assinatura raster válida.'
                previews.append(item)
                continue
            if digest(path) != expected:
                raise RuntimeError('Source screenshot hash changed while packaging')
            dest_rel = f'assets/capturas/{expected}{extension}'
            if dest_rel not in copied:
                if total + size > MAX_TOTAL_BYTES:
                    item['reason'] = 'Limite total de imagens atingido.'
                    previews.append(item)
                    continue
                target = stage / dest_rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                if digest(target) != expected:
                    raise RuntimeError('Screenshot copy failed hash verification')
                copied.add(dest_rel)
                total += size
            item.update({'status': 'AVAILABLE', 'local_path': dest_rel,
                         'sha256': expected, 'size_bytes': size, 'reason': None})
        except (OSError, ValueError):
            pass
        previews.append(item)
    return previews


def packaged_visual_files(manifest):
    """Strict, closed manifest allowlist for the screenshot package."""
    preview = manifest.get('visual_previews')
    if not isinstance(preview, list) or len(preview) > 10000:
        return None
    result = set()
    for item in preview:
        if not isinstance(item, dict):
            return None
        state = item.get('status')
        location = item.get('local_path')
        if state == 'AVAILABLE':
            if not isinstance(location, str) or not _LOCAL_PATTERN.fullmatch(location):
                return None
            if item.get('sha256') != location.split('/')[-1].split('.')[0]:
                return None
            result.add(location)
        elif state != 'UNAVAILABLE' or location is not None:
            return None
    return result


def capture_gallery_html(snapshots, previews, timezone_name):
    """Always-visible screenshot gallery with an optional fullscreen-size dialog."""
    from .components import text
    from .presentation_labels import public_value

    html = [
        '<section class="capture-visual-section" aria-label="Prévia das páginas capturadas">',
        '<h2>Prévia visual das páginas capturadas</h2>',
        '<p class="rf">Imagens originais registradas na auditoria, por dispositivo. '
        'Toque na imagem para ampliar. Nenhuma captura adicional é executada.</p>',
    ]
    if not snapshots:
        html.append('<p class="callout">Nenhuma captura de página persistida.</p>')
    for index, snapshot in enumerate(snapshots):
        item = previews[index]
        device = str(public_value(snapshot.get('device'), 'device', timezone_name))
        timestamp = public_value(snapshot.get('captured_at'), 'captured_at', timezone_name)
        address = snapshot.get('final_url') or snapshot.get('requested_url') or 'N/D'
        image = item.get('local_path')
        title = 'Captura ' + str(index + 1) + ' - ' + device
        html.append('<figure class="capture-visual">')
        html.append('<figcaption><strong>' + text(title) + '</strong>'
                    '<span>' + text(timestamp) + '</span>'
                    '<span>' + text(address) + '</span></figcaption>')
        if item.get('status') != 'AVAILABLE' or not image:
            html.append('<p class="rf capture-unavailable">Imagem não disponível: '
                        + text(item.get('reason') or 'evidência visual não persistida')
                        + '</p></figure>')
            continue
        dialog_id = 'capture-image-' + str(index)
        alt = 'Screenshot original da ' + title
        html.extend([
            '<button type="button" class="modal-open capture-image-button" '
            'data-modal="' + dialog_id + '" aria-haspopup="dialog" '
            'aria-controls="' + dialog_id + '" aria-label="Ampliar ' + text(title) + '">',
            '<img class="capture-image-preview" src="' + text(image)
            + '" alt="' + text(alt) + '" loading="lazy" decoding="async">',
            '</button><p class="rf">Clique na imagem para ampliar. '
            'SHA-256 do arquivo de origem: <code>' + text(item.get('sha256')) + '</code></p>',
            '</figure>',
            '<dialog class="detail-dialog capture-image-dialog" id="' + dialog_id
            + '" aria-labelledby="' + dialog_id + '-title">',
            '<div class="modal-head"><div><span class="modal-kicker">Captura original verificada</span>'
            '<h2 id="' + dialog_id + '-title">' + text(title) + '</h2></div>',
            '<button type="button" class="modal-close" data-modal-close '
            'aria-label="Fechar imagem">×</button></div>',
            '<div class="modal-body"><img src="' + text(image) + '" alt="' + text(alt)
            + '"><p class="rf">' + text(timestamp) + ' - ' + text(address) + '</p></div>',
            '<div class="modal-foot"><span class="rf">Imagem persistida, sem alteração.</span>'
            '<button type="button" class="modal-dismiss" data-modal-close>'
            'Fechar</button></div></dialog>',
        ])
    html.append('</section>')
    return ''.join(html)
