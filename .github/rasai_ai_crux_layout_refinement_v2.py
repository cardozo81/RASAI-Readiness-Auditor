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

# Keep the new CrUX regression fixture faithful to the production observation
# schema queried by _contexts (which orders by observation_id).
fixture_old = '''        CREATE TABLE web_performance_observations(\n          audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,normalized_url TEXT,\n          accessibility_score REAL,pagespeed_artifact_reference TEXT,error_summary TEXT,field_source TEXT\n        );'''
fixture_new = '''        CREATE TABLE web_performance_observations(\n          observation_id TEXT,audit_id TEXT,page_id TEXT,snapshot_id TEXT,device TEXT,normalized_url TEXT,\n          accessibility_score REAL,pagespeed_artifact_reference TEXT,error_summary TEXT,field_source TEXT\n        );'''
if fixture_old not in source:
    raise RuntimeError('CrUX observation fixture schema not found')
source = source.replace(fixture_old, fixture_new, 1)
insert_old = '''        db.execute("INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?)", ("AUD-X","P1","S1","MOBILE","https://example.com/",90,"artifact.json",None,"PAGESPEED_CRUX"))'''
insert_new = '''        db.execute("INSERT INTO web_performance_observations VALUES (?,?,?,?,?,?,?,?,?,?)", ("O1","AUD-X","P1","S1","MOBILE","https://example.com/",90,"artifact.json",None,"PAGESPEED_CRUX"))'''
if insert_old not in source:
    raise RuntimeError('CrUX observation fixture insert not found')
source = source.replace(insert_old, insert_new, 1)

exec(compile(source, str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
