"""Bounded presentation adapter over captured bytes, including partial audits.

The terminal-AUD gate belongs to the private companion, not this derived view.
Reuse its offline worker and structural contracts without invoking its loader,
search correlation, providers, persistence or collectors. No process-wide cache.
"""
import base64
from hashlib import sha256
import json
import re
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit

from rasai.contextual_advisory import _worker
from rasai.contextual_content import MAX_BYTES
from rasai.contextual_semantics import report_overlay
from rasai.contextual_faq_aria import report_overlay as faq_overlay
from rasai.contextual_page_structure import report_overlay as structure_overlay
from rasai.contextual_reverse_review import review_projection
from .artifact_reader import confined
from .sanitization import sanitize


def state_label(state):
    from .presentation_labels import STATUS_LABELS
    return {
        'SOURCE_ABSENT': 'Fonte ausente ou referência não verificável',
        'SOURCE_INTEGRITY_MISMATCH': 'Integridade da fonte divergente',
        'PROJECTION_ERROR': 'Erro na projeção offline',
        'RESOURCE_LIMIT': 'Limite de recursos da projeção',
        'MATERIALIZED_NO_PERTINENT_PROJECTION': 'Fonte materializada sem série comparável suficiente',
        'INCOMPLETE': 'Incompleta',
    }.get(state, STATUS_LABELS.get(state, state or 'N/D'))


def public_text(value):
    """Redact captured credentials, local paths and URL queries before escaping."""
    if not isinstance(value, str):
        return value
    value = sanitize(value)
    if not isinstance(value, str):
        return public_data(value)
    value = re.sub(r'(?i)(?:(?<![A-Za-z0-9])[a-z]:[\\/]|\\\\)[^\s<>"\']+', '[PRIVATE PATH]', value)
    value = re.sub(r'/(?:home|Users|tmp|var)/[^\s<>"\']+', '[PRIVATE PATH]', value)
    def clean(match):
        try:
            p = urlsplit(match[0])
            if not p.hostname or p.username or p.password:
                return '[REDACTED URL]'
            return urlunsplit((p.scheme, p.netloc, p.path, '', ''))
        except ValueError:
            return '[REDACTED URL]'
    return re.sub(r'https?://[^\s<>"\']+', clean, value)


def public_data(value):
    if isinstance(value, dict):
        return {k: public_data(v) for k, v in sanitize(value).items()}
    if isinstance(value, (list, tuple)):
        return [public_data(v) for v in value]
    return public_text(value)


def object_value(value):
    if isinstance(value, dict):
        return value
    try:
        result = json.loads(value) if isinstance(value, str) else None
        return result if isinstance(result, dict) else {}
    except (ValueError, RecursionError):
        return {}


def read_source(root, ref, inventory, *, expected=None, limit=MAX_BYTES):
    """Verify bounded bytes against the generation inventory and persisted hash."""
    if not isinstance(ref, str) or not ref.startswith('artifacts/'):
        return None, 'SOURCE_ABSENT'
    try:
        path = confined(root, ref)
        if not path.is_file():
            return None, 'SOURCE_ABSENT'
        if path.stat().st_size > limit:
            return None, 'RESOURCE_LIMIT'
        with path.open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return None, 'RESOURCE_LIMIT'
        actual = sha256(raw).hexdigest()
        if inventory.get(ref) != actual or (expected and expected != actual):
            return None, 'SOURCE_INTEGRITY_MISMATCH'
        return raw, 'AVAILABLE'
    except (OSError, ValueError):
        return None, 'SOURCE_ABSENT'


def project_capture(root, tables, inventory):
    result = dict(state='SOURCE_ABSENT', captures=[], sources=[],
                  network_requests=0, provider_calls=0, audit_writes=0,
                  limitations=['STRUCTURAL_EXTRACTION_ONLY', 'NOT_SEMANTIC_ASSESSMENT'])
    snapshots = tables.get('page_snapshots', ())
    if not snapshots:
        return result
    audit_id = next(iter(tables.get('audits', ())), {}).get('audit_id')
    deadline, total, emitted = time.monotonic() + 30, 0, 0
    for snapshot in snapshots[:200]:
        source = dict(snapshot_id=snapshot.get('snapshot_id'), table='page_snapshots',
                      scope=snapshot.get('device'), state='SOURCE_ABSENT')
        result['sources'].append(source)
        if time.monotonic() > deadline or total >= 20_000_000:
            source['state'] = 'RESOURCE_LIMIT'
            continue
        metadata = object_value(snapshot.get('browser_metadata'))
        binding = object_value(metadata.get('architecture_artifact_binding'))
        for field, surface, hash_field in (
            ('rendered_artifact_ref', 'RENDERED_DOM', 'rendered_sha256'),
            ('raw_artifact_ref', 'RAW_HTML_FALLBACK', 'raw_sha256'),
        ):
            ref = snapshot.get(field)
            if not ref:
                continue
            expected = binding.get(hash_field)
            if field == 'rendered_artifact_ref':
                expected = expected or object_value(metadata.get('rendered_dom')).get('sha256')
            raw, state = read_source(root, ref, inventory, expected=expected,
                                     limit=min(MAX_BYTES, 20_000_000 - total))
            source.update(state=state, field=field)
            if state == 'SOURCE_INTEGRITY_MISMATCH':
                break  # Never silently replace a corrupt bound DOM with RAW.
            if raw is None:
                continue
            total += len(raw)
            source.update(reference=ref, sha256=sha256(raw).hexdigest(), surface=surface)
            required = ('snapshot_id', 'page_id', 'device', 'requested_url', 'captured_at')
            if not all(isinstance(snapshot.get(k), str) and 0 < len(snapshot[k]) <= 4096 for k in required):
                source['state'] = 'PROJECTION_ERROR'
                source['cause'] = 'SNAPSHOT_CONTRACT_INCOMPLETE'
                break
            try:
                packet = _worker(dict(audit_id=audit_id, **{k: snapshot[k] for k in required},
                    final_url=snapshot.get('final_url'), original=base64.b64encode(raw).decode('ascii'),
                    source_ref=ref, surface=surface))
                if (not isinstance(packet, dict) or packet.get('source_sha256') != source['sha256']
                        or packet.get('snapshot_id') != snapshot['snapshot_id']):
                    raise ValueError('worker contract')
                occurrences = packet.get('occurrences') or []
                remaining = max(0, 2000 - emitted)
                if len(occurrences) > remaining:
                    packet['occurrences'] = occurrences[:remaining]
                    packet.setdefault('limitations', []).append('AUD_OCCURRENCE_LIMIT_PARTIAL')
                emitted += len(packet.get('occurrences', ()))
                structure = packet.get('page_structure_overlay_v3') or {}
                source['state'] = ('AVAILABLE' if structure.get('coverage') == 'CAPTURE_INSPECTED'
                                   else 'PROJECTION_ERROR')
                limits = packet.get('limitations', []) + structure.get('limitations', [])
                if source['state'] == 'AVAILABLE' and any('PARTIAL' in x for x in limits):
                    source['state'] = 'PARTIAL'
                source['limitations'] = limits
                result['captures'].append(packet)
            except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as exc:
                source.update(state='PROJECTION_ERROR', cause=(
                    'WORKER_TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'OFFLINE_WORKER_ERROR'))
            break
        # Optional materialized sidecars have their own state; failure cannot erase DOM facts.
        for field in ('main_content_ref', 'structured_data_ref'):
            ref = snapshot.get(field)
            if not ref:
                continue
            raw, state = ((None, 'RESOURCE_LIMIT') if time.monotonic() > deadline or total >= 20_000_000
                          else read_source(root, ref, inventory, limit=min(MAX_BYTES, 20_000_000-total)))
            sidecar = dict(table='page_snapshots', snapshot_id=snapshot.get('snapshot_id'),
                           field=field, reference=ref if ref in inventory else None,
                           sha256=inventory.get(ref), state=state)
            result['sources'].append(sidecar)
            if raw is None:
                continue
            total += len(raw)
            try:
                if field == 'main_content_ref':
                    value = raw.decode('utf-8')
                    sidecar.update(characters=len(value), excerpt=value[:600], excerpt_omitted=max(0,len(value)-600))
                else:
                    value = json.loads(raw)
                    if not isinstance(value, (dict, list)):
                        raise ValueError('structured sidecar contract')
                    stack, types, nodes = [value], set(), 0
                    while stack:
                        node = stack.pop()
                        nodes += 1
                        if nodes > 5000:
                            raise ValueError('structured sidecar node limit')
                        if isinstance(node, dict):
                            kind = node.get('@type')
                            if isinstance(kind, str):
                                types.add(kind[:200])
                            elif isinstance(kind, list):
                                types.update(k[:200] for k in kind if isinstance(k, str))
                            stack.extend(node.values())
                        elif isinstance(node, list):
                            stack.extend(node)
                    sidecar.update(observed_types=sorted(types), container='JSON_SIDECAR')
            except (ValueError, UnicodeError, RecursionError):
                sidecar.update(state='PROJECTION_ERROR', cause='SIDECAR_CONTRACT_INVALID')
    states = [s['state'] for s in result['sources']]
    if len(snapshots) > 200:
        result['limitations'].append('SNAPSHOT_LIMIT_PARTIAL')
    result['state'] = ('SOURCE_INTEGRITY_MISMATCH' if 'SOURCE_INTEGRITY_MISMATCH' in states else
                       'AVAILABLE' if states and all(s == 'AVAILABLE' for s in states) and len(snapshots) <= 200 else
                       'PARTIAL' if result['captures'] else
                       'PROJECTION_ERROR' if 'PROJECTION_ERROR' in states else
                       'RESOURCE_LIMIT' if 'RESOURCE_LIMIT' in states else 'SOURCE_ABSENT')
    captures = result['captures']
    result['semantic_v2'] = report_overlay(captures, [])
    result['faq_aria_v3'] = faq_overlay(captures)
    result['content_structure_v3'] = structure_overlay(captures)
    # Conditional human checks over structure, not a semantic engine execution.
    result['reverse_review'] = review_projection(result)
    return public_data(result)
