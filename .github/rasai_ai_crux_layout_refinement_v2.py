from __future__ import annotations

from pathlib import Path

path = Path('.github/rasai_ai_crux_layout_refinement.py')
source = path.read_text(encoding='utf-8')
old = '''def regex_once(text: str, pattern: str, repl: str, *, label: str) -> str:\n    result, count = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)\n    if count != 1:\n        raise RuntimeError(f"{label}: expected exactly one match, got {count}")\n    return result\n'''
new = '''def regex_once(text: str, pattern: str, repl: str, *, label: str) -> str:\n    pattern = pattern.replace("\\\\\\\\", "\\\\")\n    result, count = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)\n    if count != 1:\n        raise RuntimeError(f"{label}: expected exactly one match, got {count}")\n    return result\n'''
if old not in source:
    raise RuntimeError('regex_once source contract not found')
source = source.replace(old, new, 1)
exec(compile(source, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
