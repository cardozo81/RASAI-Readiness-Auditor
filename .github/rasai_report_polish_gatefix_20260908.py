from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    text = read(path)
    actual = text.count(old)
    if actual != count:
        raise RuntimeError(f"expected {count} occurrence(s) in {path}, found {actual}: {old[:100]!r}")
    write(path, text.replace(old, new, count))


# The public-contract gate must assert the same comprehension-first order that
# report_contract.py now defines. This strengthens the gate instead of bypassing it.
replace(
    "src/rasai/public_contract_gate.py",
    '''EXPECTED_CANONICAL_FILENAMES = (\n    "index.html",\n    "readiness.html",\n    "scoring.html",\n    "mobile.html",\n    "desktop.html",\n    "remediation.html",\n    "content-suggestions.html",\n    "crawling-discovery.html",\n    "accessibility.html",\n    "web-performance.html",\n    "apdex.html",\n    "apdex-experience.html",\n    "ai-visibility.html",\n    "observability.html",\n    "quality.html",\n    "ai-usage.html",\n    "references.html",\n)\n''',
    '''EXPECTED_CANONICAL_FILENAMES = (\n    "index.html",\n    "readiness.html",\n    "scoring.html",\n    "mobile.html",\n    "desktop.html",\n    "crawling-discovery.html",\n    "accessibility.html",\n    "web-performance.html",\n    "apdex.html",\n    "apdex-experience.html",\n    "content-suggestions.html",\n    "remediation.html",\n    "ai-usage.html",\n    "ai-visibility.html",\n    "observability.html",\n    "quality.html",\n    "references.html",\n)\n''',
)
replace(
    "src/rasai/public_contract_gate.py",
    '''The gate validates public/runtime invariants without rewriting files. Historical\nmethod references remain allowed when clearly marked as historical; current\nsurfaces may not present an older method as the active runtime.\n''',
    '''The gate validates public/runtime invariants without rewriting files. References\nto earlier development proposals remain allowed when clearly qualified; current\nsurfaces may not present an earlier proposal as the active runtime.\n''',
)

# Keep the artifact inventory in the same reading order as the canonical menu.
replace(
    "docs/OUTPUTS_AND_ARTIFACTS.md",
    '''   ├─ mobile.html              # condicional\n   ├─ desktop.html             # condicional\n   ├─ remediation.html\n   ├─ content-suggestions.html\n   ├─ crawling-discovery.html  # condicional\n   ├─ accessibility.html       # condicional\n   ├─ web-performance.html     # condicional\n   ├─ apdex.html               # condicional\n   ├─ apdex-experience.html    # condicional\n   ├─ ai-visibility.html       # condicional\n   ├─ observability.html       # condicional\n   ├─ quality.html             # condicional\n   ├─ ai-usage.html\n   ├─ references.html\n''',
    '''   ├─ mobile.html              # condicional\n   ├─ desktop.html             # condicional\n   ├─ crawling-discovery.html  # condicional\n   ├─ accessibility.html       # condicional\n   ├─ web-performance.html     # condicional\n   ├─ apdex.html               # condicional\n   ├─ apdex-experience.html    # condicional\n   ├─ content-suggestions.html\n   ├─ remediation.html\n   ├─ ai-usage.html\n   ├─ ai-visibility.html       # condicional\n   ├─ observability.html       # condicional\n   ├─ quality.html             # condicional\n   ├─ references.html\n''',
)
replace(
    "docs/OUTPUTS_AND_ARTIFACTS.md",
    "Nenhuma projeção recalcula silenciosamente auditoria histórica para outra `scoring_version`.",
    "Nenhuma projeção recalcula silenciosamente uma auditoria persistida para outra `scoring_version`.",
)

# Global row-state helper must remain idempotent if report normalization runs more
# than once. Treat requested classes individually instead of as one compound token.
replace(
    "src/rasai/report_semantics.py",
    '''    classes = match.group("classes").split()\n    if class_name not in classes:\n        classes.append(class_name)\n    replacement = f" class={match.group('q')}{' '.join(classes)}{match.group('q')}"\n''',
    '''    classes = match.group("classes").split()\n    for requested in class_name.split():\n        if requested not in classes:\n            classes.append(requested)\n    replacement = f" class={match.group('q')}{' '.join(classes)}{match.group('q')}"\n''',
)

# Add an explicit idempotency regression for the central state decorator.
test_path = "tests/test_report_polish_20260908.py"
test_text = read(test_path)
marker = "def test_actionable_table_rows_are_idempotent()"
if marker not in test_text:
    test_text += '''\n\ndef test_actionable_table_rows_are_idempotent() -> None:\n    html = "<table><tbody><tr><td>BR-GEO-017</td><td>Alerta</td></tr></tbody></table>"\n    once = enhance_report_html(html, page_name="scoring.html", report_dir=ROOT)\n    twice = enhance_report_html(once, page_name="scoring.html", report_dir=ROOT)\n    assert twice.count("result-state-warn") == once.count("result-state-warn")\n    assert twice.count("result-cell warn") == once.count("result-cell warn")\n    assert twice.count("result-tag warn") == once.count("result-tag warn")\n'''
    write(test_path, test_text)

# The gate's static order and the registry must be intentionally identical.
contract = read("src/rasai/report_contract.py")
gate = read("src/rasai/public_contract_gate.py")
expected_order = [
    "index.html", "readiness.html", "scoring.html", "mobile.html", "desktop.html",
    "crawling-discovery.html", "accessibility.html", "web-performance.html", "apdex.html",
    "apdex-experience.html", "content-suggestions.html", "remediation.html", "ai-usage.html",
    "ai-visibility.html", "observability.html", "quality.html", "references.html",
]
last = -1
for filename in expected_order:
    pos = contract.find(f'filename="{filename}"')
    if pos <= last:
        raise RuntimeError(f"report_contract order mismatch at {filename}")
    last = pos
last = -1
for filename in expected_order:
    pos = gate.find(f'    "{filename}",')
    if pos <= last:
        raise RuntimeError(f"public_contract_gate order mismatch at {filename}")
    last = pos

print("RASAi public contract gate alignment applied successfully")
