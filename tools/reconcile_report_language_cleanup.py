from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    # Markdown hard line breaks are not required by the project contract; strip
    # trailing whitespace so git diff hygiene remains deterministic.
    normalized = "\n".join(line.rstrip() for line in text.splitlines()).rstrip() + "\n"
    (ROOT / path).write_text(normalized, encoding="utf-8", newline="\n")


# Reconcile the normative index with the state already integrated in main.
index_path = "docs/specification/00_SPEC_INDEX.md"
text = read(index_path)
text = re.sub(
    r"^\*\*Status:\*\* APPROVED BASELINE.*$",
    "**Status:** BASELINE VIGENTE — capacidades integradas e documentação reconciliada com `main`.",
    text,
    count=1,
    flags=re.MULTILINE,
)
text = text.replace("EM BRANCH", "INTEGRADO")
text = re.sub(
    r"- está em implementação na branch `[^`]+`;",
    "- está integrado à baseline vigente;",
    text,
)
text = text.replace("**Milestone:**", "**Capacidade:**")
write(index_path, text)

# Remove delivery-process vocabulary from capability specifications where it
# survived as a field label after the Mxx identifier was translated.
for path in (
    "docs/specification/14_MULTI_URL_VISUAL_EVIDENCE_REMEDIATION.md",
    "docs/specification/15_ERROR_CENTRIC_REPORT_UX.md",
    "docs/specification/16_ROOT_CAUSE_ELEMENT_REMEDIATION.md",
    "docs/specification/17_REMEDIATION_PRECISION_REPORT_CONSISTENCY.md",
):
    text = read(path).replace("**Milestone:**", "**Capacidade:**")
    write(path, text)

for path in (
    "docs/specification/20_AI_CONTENT_REMEDIATION.md",
    "docs/specification/21_EXTERNAL_WEB_PERFORMANCE_EVIDENCE.md",
    "docs/specification/22_DOMAIN_SEPARATED_WEB_QUALITY_DIAGNOSTICS.md",
    "docs/specification/23_SYNTHETIC_APDEX_LIGHTHOUSE_TRACEABILITY.md",
    "docs/specification/24_CRAWLING_DISCOVERY_AI_ACCESS.md",
    "docs/specification/25_SYNTHETIC_USER_EXPERIENCE_APDEX.md",
    "docs/specification/26_OBSERVED_GENERATIVE_VISIBILITY.md",
):
    text = read(path)
    text = text.replace("**Identifier:**", "**Domínio:**")
    text = text.replace("**Identificador:**", "**Domínio:**")
    text = text.replace("EM BRANCH", "INTEGRADO")
    text = text.replace("aguardando smoke humano antes de merge", "integrado e validado")
    write(path, text)

# Apply whitespace hygiene to every user/documentation Markdown file changed by
# the reconciliation, not only to the known examples above.
for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
    content = path.read_text(encoding="utf-8")
    normalized = "\n".join(line.rstrip() for line in content.splitlines()).rstrip() + "\n"
    path.write_text(normalized, encoding="utf-8", newline="\n")
