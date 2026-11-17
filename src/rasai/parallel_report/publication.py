"""Validate the offline package and publish one complete tree per audit."""
from contextlib import contextmanager
from hashlib import sha256
import json
import os
import re
import shutil

from . import __version__
from .artifact_reader import DIRECTORY, WORK_DIRECTORY, confined, digest, tree_digest
from .read_model import PAGES
from .capture_gallery import packaged_visual_files

MANIFEST = '_geracao.json'
CONTRACT = 'RASAI-PARALLEL-REPORT-001'
DATED = re.compile(r'[0-9]{8}-[0-9]{6}(?:-[0-9]+)?')


def plain_directory(path):
    if path.is_symlink() or path.is_junction() or (path.exists() and not path.is_dir()):
        raise ValueError('Unsafe presentation directory')
    return path


def historical_directories(base):
    plain_directory(base)
    if not base.is_dir():
        return []
    return sorted((plain_directory(p) for p in base.iterdir() if DATED.fullmatch(p.name)),
                  reverse=True)


def relevant_sources(inventory, evidence):
    # Operational messages can be appended after finalization. Count a log only
    # if it was actually referenced as evidence by the presentation.
    referenced = {str(item.get('reference', '')).replace('\\', '/').removeprefix('./')
                  for item in evidence if isinstance(item, dict)}
    # The catalog is a sibling *derived* HTML package, never a source of
    # facts for the standalone presentation. Do not invalidate a verified
    # presentation merely because the catalog was rebuilt or failed to publish.
    return {name: value for name, value in inventory.items()
            if name != 'audit.db' and not name.startswith('report-catalog/')
            and (name in referenced or not name.startswith('logs/'))}


def compatible_manifest(directory, source, logical, *, historical_version=False):
    """Trust only a complete package from this renderer and the current inputs."""
    try:
        path = confined(directory, MANIFEST)
        manifest = json.loads(path.read_text(encoding='utf-8'))
        versions = (__version__, '0.4.18', '0.4.17', '0.4.16', '0.4.3', '0.4.2', '0.4.1', '0.3.0', '0.2.0', '0.1.0') if historical_version else (__version__,)
        if not isinstance(manifest, dict) or (
            manifest.get('contract') != CONTRACT or manifest.get('version') != 1
            or manifest.get('generator_version') not in versions
            or manifest.get('integrity') != 'PASS'
            or manifest.get('source_db_logical_sha256') != logical
        ):
            return None
        recorded = manifest['source_inventory']
        recorded_digest = tree_digest(recorded)
        if (manifest.get('source_tree_digest_before') != recorded_digest
                or manifest.get('source_tree_digest_after') != recorded_digest):
            return None
        evidence = manifest['artifacts_read']
        if relevant_sources(recorded, evidence) != relevant_sources(source, evidence):
            return None
        visual_files = packaged_visual_files(manifest)
        if visual_files is None:
            return None
        required = {name + '.html' for name, _ in PAGES}
        required.update(visual_files)
        required.update('assets/' + name for name in ('site.css', 'app.js', 'thresholds.json',
                                                          'coverage-map.json', 'evidence-coverage.json'))
        required.update('anexos/' + sha256(table.encode()).hexdigest() + '.json'
                        for table in manifest['tables_read'])
        hashes = manifest['sha256_per_file']
        if set(hashes) != required or set(manifest['generated_files']) != required:
            return None
        if all(digest(confined(directory, name)) == hashes[name] for name in required):
            return manifest
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return None


def find_package(base, historical, source, logical, *, historical_version=False):
    for directory in [base, *historical]:
        manifest = compatible_manifest(directory, source, logical, historical_version=historical_version)
        if manifest is not None:
            return directory, manifest
    return None


@contextmanager
def publication_work(root):
    # Stage on the destination filesystem. Keep the lock
    # inode stable across publishers. The OS releases it even on process death.
    work = plain_directory(root / WORK_DIRECTORY)
    work.mkdir(mode=0o700, exist_ok=True)
    lock = work / 'publication.lock'
    if lock.is_symlink() or lock.is_junction():
        raise ValueError('Linked publication lock')
    with lock.open('a+b') as stream:
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
        base = plain_directory(root / DIRECTORY)
        previous = plain_directory(work / 'previous')
        if previous.exists() and not base.exists():
            previous.rename(base)
        # A visible destination alongside a backup means the staged rename
        # succeeded before interruption. The destination was already verified.
        if previous.exists():
            shutil.rmtree(previous)
        stage = plain_directory(work / 'stage')
        if stage.exists():
            shutil.rmtree(stage)
        try:
            yield stage, previous
        finally:
            if stage.exists():
                shutil.rmtree(stage)


def publish(stage, base, previous):
    if base.exists():
        base.rename(previous)
    try:
        stage.rename(base)
    except BaseException:
        if previous.exists():
            previous.rename(base)
        raise
    if previous.exists():
        shutil.rmtree(previous)
