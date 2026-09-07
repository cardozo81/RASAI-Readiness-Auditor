from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

GENERAL_REPLACEMENTS = {
    "Rastreamento, descoberta e acesso de crawlers Crawling, Discovery & AI Access": "Rastreamento, descoberta e acesso de crawlers",
    "Crawling, Discovery & AI Access — Rastreamento, descoberta e acesso de crawlers": "Rastreamento e descoberta",
    "Synthetic Navigation Apdex Synthetic Navigation Apdex": "Synthetic Navigation Apdex",
    "Synthetic User Experience Apdex Synthetic User Experience Apdex": "Synthetic User Experience Apdex",
    "Synthetic Navigation Apdex/Synthetic User Experience Apdex Apdex": "Synthetic Navigation Apdex e Synthetic User Experience Apdex",
    "Observed Generative Visibility Observed Generative Visibility": "Observed Generative Visibility",
    "Observed Generative Visibility Observed Visibility": "Observed Generative Visibility",
    "Observed Generative Visibility — Observed Generative Visibility": "Observed Generative Visibility",
    "Synthetic Navigation Apdex — Synthetic Navigation Apdex": "Synthetic Navigation Apdex",
    "Synthetic User Experience Apdex — Synthetic User Experience Apdex": "Synthetic User Experience Apdex",
    "Synthetic Apdex Synthetic Navigation Apdex": "Synthetic Navigation Apdex",
    "Rastreamento, descoberta e acesso de crawlers crawling/discovery": "rastreamento e descoberta",
    "diagnósticos Rastreamento, descoberta e acesso de crawlers": "diagnósticos de rastreamento e descoberta",
    "telemetria de IA Rastreamento, descoberta e acesso de crawlers": "telemetria dessa remediação técnica por IA",
    "remediação técnica por IA Rastreamento, descoberta e acesso de crawlers": "remediação técnica de rastreamento e descoberta por IA",
    "finalidade Rastreamento, descoberta e acesso de crawlers": "finalidade de rastreamento e descoberta",
    "remediação textual Sugestões e remediação de conteúdo por IA": "remediação textual por IA",
}

DOC_REPLACEMENTS = {
    "## Crawling, Discovery & AI Access": "## Rastreamento e descoberta",
    "### Rastreamento, descoberta e acesso de crawlers — crawling/discovery": "### Rastreamento e descoberta",
    "### Synthetic Apdex Synthetic Navigation Apdex": "### Synthetic Navigation Apdex",
    "### Synthetic User Experience Apdex Synthetic User Experience Apdex": "### Synthetic User Experience Apdex",
    "### Observed Generative Visibility Observed Generative Visibility": "### Observed Generative Visibility",
    "## Rastreamento, descoberta e acesso de crawlers — remediação técnica de crawling/discovery por IA": "## Remediação técnica de rastreamento e descoberta por IA",
    "### Remediação técnica Rastreamento, descoberta e acesso de crawlers por IA": "### Remediação técnica de rastreamento e descoberta por IA",
    "Os diagnósticos determinísticos Rastreamento, descoberta e acesso de crawlers executam": "Os diagnósticos determinísticos de rastreamento e descoberta executam",
    "Essa opção **não habilita o Rastreamento, descoberta e acesso de crawlers determinístico**": "Essa opção **não habilita os diagnósticos determinísticos de rastreamento e descoberta**",
    "Rastreamento, descoberta e acesso de crawlers aprofunda o diagnóstico técnico de descoberta": "O diagnóstico de rastreamento e descoberta aprofunda a análise técnica de descoberta",
    "Essa página é não-scoring:": "Essa página é informativa e não altera o SearchGEO Readiness Index:",
    "`/llms.txt` como proposta comunitária experimental e **non-scoring**": "`/llms.txt` como proposta comunitária experimental; sua presença ou ausência **não altera o SearchGEO Readiness Index**",
    "Observed Generative Visibility, sem alterar scoring:": "Observed Generative Visibility (domínio separado do SGRI):",
    "| Crawling/Discovery/AI Access |": "| Rastreamento e descoberta |",
    "O parâmetro Rastreamento, descoberta e acesso de crawlers `--ai-technical-remediation`": "O parâmetro `--ai-technical-remediation`",
}

CONSOLE_REPLACEMENTS = {
    "Ativa Sugestões e remediação de conteúdo por IA advisory para findings elegíveis": "Ativa sugestões e remediação de conteúdo por IA para findings elegíveis",
    "Default do Sugestões e remediação de conteúdo por IA textual.": "Default da remediação textual por IA.",
    "Web Performance externo/Lighthouse": "Web Performance/Lighthouse",
    "Web Performance externo:": "Web Performance:",
}


def apply(path: Path, replacements: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8", newline="\n")


for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
    apply(path, GENERAL_REPLACEMENTS)
    apply(path, DOC_REPLACEMENTS)

for name in ("console_help.py", "report_navigation.py", "report_semantics.py", "m18_reporting.py", "m20_reporting.py", "m21_reporting.py", "m22_quality_domains.py", "m23_reporting.py", "m24_reporting.py", "m25_reporting.py", "m26_reporting.py"):
    path = ROOT / "src" / "searchgeo" / name
    if path.exists():
        apply(path, GENERAL_REPLACEMENTS)

apply(ROOT / "src" / "searchgeo" / "console_help.py", CONSOLE_REPLACEMENTS)

# Presentation/documentation guard: no delivery milestone labels in product docs,
# and no known mechanical replacement artifacts.
milestone = re.compile(r"(?<![\w-])M\d{1,2}(?![\w-])")
forbidden = (
    "Synthetic Navigation Apdex Synthetic Navigation Apdex",
    "Synthetic User Experience Apdex Synthetic User Experience Apdex",
    "Observed Generative Visibility Observed Generative Visibility",
    "Observed Generative Visibility Observed Visibility",
    "Rastreamento, descoberta e acesso de crawlers Crawling, Discovery & AI Access",
    "Synthetic Navigation Apdex/Synthetic User Experience Apdex Apdex",
)

problems: list[str] = []
for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]:
    text = path.read_text(encoding="utf-8")
    reasons: list[str] = []
    if milestone.search(text):
        reasons.append("delivery label Mxx")
    for token in forbidden:
        if token in text:
            reasons.append(token)
    if reasons:
        problems.append(f"{path.relative_to(ROOT)}: {', '.join(reasons)}")
if problems:
    raise SystemExit("public language cleanup guard failed:\n" + "\n".join(problems))
