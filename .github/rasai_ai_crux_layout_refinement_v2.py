from __future__ import annotations

from pathlib import Path

path = Path('.github/rasai_ai_crux_layout_refinement.py')
source = path.read_text(encoding='utf-8')

old_regex = '''def regex_once(text: str, pattern: str, repl: str, *, label: str) -> str:\n    result, count = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)\n    if count != 1:\n        raise RuntimeError(f"{label}: expected exactly one match, got {count}")\n    return result\n'''
new_regex = '''def regex_once(text: str, pattern: str, repl: str, *, label: str) -> str:\n    pattern = pattern.replace("\\\\\\\\", "\\\\")\n    result, count = re.subn(pattern, repl, text, count=1, flags=re.DOTALL)\n    if count != 1:\n        raise RuntimeError(f"{label}: expected exactly one match, got {count}")\n    return result\n'''
if old_regex in source:
    source = source.replace(old_regex, new_regex, 1)

old_gemini = '''text = replace_once(\n    text,\n    '                "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),\\n',\n    '                "schema": gemini_wire_schema(hardened_semantic_output_schema(semantic_input.allowed_evidence_ids)),\\n',\n    label="Gemini semantic wire schema",\n)'''
new_gemini = '''text = replace_once(\n    text,\n    '            "response_format": {\\n                "type": "text",\\n                "mime_type": "application/json",\\n                "schema": hardened_semantic_output_schema(semantic_input.allowed_evidence_ids),\\n            },',\n    '            "response_format": {\\n                "type": "text",\\n                "mime_type": "application/json",\\n                "schema": gemini_wire_schema(hardened_semantic_output_schema(semantic_input.allowed_evidence_ids)),\\n            },',\n    label="Gemini semantic wire schema",\n)'''
if old_gemini not in source:
    raise RuntimeError('Gemini source patch contract not found')
source = source.replace(old_gemini, new_gemini, 1)

exec(compile(source, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
