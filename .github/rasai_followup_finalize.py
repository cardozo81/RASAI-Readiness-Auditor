from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str) -> None:
    target = ROOT / path
    value = target.read_text(encoding="utf-8")
    if old not in value:
        raise RuntimeError(f"anchor not found in {path}: {old!r}")
    target.write_text(value.replace(old, new, 1), encoding="utf-8", newline="\n")


# Contract count changed because RASAI_AI_TECHNICAL_REMEDIATION became a first-class
# console variable alongside RASAI_AI_CONTENT_REMEDIATION.
replace(
    "tests/test_console_environment_guidance.py",
    "    assert len(ENV_NAMES) == 52\n",
    "    assert len(ENV_NAMES) == 53\n",
)

# Internal delivery/module identifiers must not leak into public documentation/templates.
replace(
    "docs/SCORING_GUIDE.md",
    "Os diagnósticos aprofundados M24 continuam advisory/non-scoring; isso não remove a participação das regras determinísticas básicas no SARI.",
    "Os diagnósticos aprofundados de crawling/discovery continuam advisory/non-scoring; isso não remove a participação das regras determinísticas básicas no SARI.",
)
replace(
    "src/rasai/m24_reporting.py",
    "Os diagnósticos M24 aprofundados permanecem advisory/non-scoring.",
    "Os diagnósticos aprofundados de crawling/discovery permanecem advisory/non-scoring.",
)

print("post-smoke finalizer applied")
