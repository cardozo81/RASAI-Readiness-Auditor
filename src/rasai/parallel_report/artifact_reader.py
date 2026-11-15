"""Confined reads and full physical inventory, including the canonical report."""
from hashlib import sha256
from pathlib import Path, PureWindowsPath
import json
import os


DIRECTORY = 'report-presentation'
WORK_DIRECTORY = '.report-presentation-work'


def digest(path):
    with path.open('rb') as stream:
        result = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def confined(root, reference):
    root = root.resolve(strict=True)
    ref = str(reference)
    if not ref or PureWindowsPath(ref).is_absolute() or ':' in ref or '\x00' in ref:
        raise ValueError('Unsafe artifact reference')
    candidate = root / ref.replace('\\', '/')
    if '..' in candidate.relative_to(root).parts:
        raise ValueError('Path traversal')
    current = root
    for part in candidate.relative_to(root).parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError('Linked source paths are not supported')
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError('Artifact outside audit root')
    return resolved


def inventory(root):
    result = {}
    for directory, folders, files in os.walk(root, followlinks=False):
        base = Path(directory)
        if base == root:
            folders[:] = [name for name in folders if name not in {DIRECTORY, WORK_DIRECTORY}]
        for name in folders + files:
            item = base / name
            if item.is_symlink() or item.is_junction():
                raise ValueError('Linked source paths are not supported')
        for name in sorted(files):
            path = base / name
            result[path.relative_to(root).as_posix()] = digest(path)
    return dict(sorted(result.items()))


def tree_digest(records, prefix=''):
    selected = {k: v for k, v in records.items() if k.startswith(prefix)}
    return sha256(json.dumps(selected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
