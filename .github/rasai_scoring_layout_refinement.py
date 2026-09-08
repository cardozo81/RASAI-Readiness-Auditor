from __future__ import annotations

from pathlib import Path

ROOT = Path('.')
TARGET = ROOT / 'src/rasai/score_geo_004_reporting.py'
TEST = ROOT / 'tests/test_scoring_report_layout_20260908.py'


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f'expected target not found: {old[:120]!r}')
    return text.replace(old, new, 1)


text = TARGET.read_text(encoding='utf-8')

text = replace_once(
    text,
    '''_DIMENSION_LABELS = {
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
}
''',
    '''_DIMENSION_LABELS = {
    "TECHNICAL_ACCESSIBILITY": "Acessibilidade técnica",
    "INDEXABILITY": "Capacidade de indexação",
    "CONTENT_EXTRACTABILITY": "Extração de conteúdo",
    "SEMANTIC_STRUCTURE": "Estrutura semântica",
    "ENTITY_CLARITY": "Clareza de entidades",
    "STRUCTURED_DATA": "Dados estruturados",
    "ANSWERABILITY": "Capacidade de resposta",
    "CITATION_READINESS": "Preparação para citação",
    "EVIDENCE_TRUST": "Evidências e confiabilidade",
    "INTENT_COVERAGE": "Cobertura de intenções",
}

# Page-scoped layout: scoring contribution tables need substantially more horizontal
# space than generic report cards. Keeping this CSS local prevents a scoring-specific
# readability requirement from changing the layout contract of the other reports.
_SCORING_LAYOUT_CSS = r"""
.scoring-weight-groups{display:flex;flex-direction:column;gap:16px;margin-top:16px}
.scoring-dimension-panel{width:100%;min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(47,58,78,.025)}
.scoring-dimension-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:14px 16px;background:#f7f8fb;border-bottom:1px solid var(--line)}
.scoring-dimension-heading h4{margin:0;font-size:1rem;line-height:1.3}
.scoring-dimension-meta{color:var(--muted);font-size:.76rem;white-space:nowrap}
.scoring-dimension-table{margin:0!important;border:0!important;border-radius:0!important;overflow-x:auto;overflow-y:visible;max-height:none!important}
.scoring-dimension-table table{width:100%;min-width:940px;table-layout:fixed}
.scoring-dimension-table th,.scoring-dimension-table td{padding:11px 12px;line-height:1.45}
.scoring-dimension-table th:nth-child(1),.scoring-dimension-table td:nth-child(1){width:112px}
.scoring-dimension-table th:nth-child(2),.scoring-dimension-table td:nth-child(2){width:auto;min-width:300px}
.scoring-dimension-table th:nth-child(3),.scoring-dimension-table td:nth-child(3){width:190px}
.scoring-dimension-table th:nth-child(4),.scoring-dimension-table td:nth-child(4){width:72px;text-align:center}
.scoring-dimension-table th:nth-child(5),.scoring-dimension-table td:nth-child(5){width:110px}
.scoring-dimension-table th:nth-child(6),.scoring-dimension-table td:nth-child(6){width:72px;text-align:center}
.scoring-dimension-table th:nth-child(7),.scoring-dimension-table td:nth-child(7){width:142px;text-align:right}
.scoring-dimension-table td:nth-child(2){color:#3f4c60}
.scoring-dimension-table td:nth-child(3) code{white-space:normal;overflow-wrap:anywhere;word-break:break-word}
.scoring-dimension-table td:nth-child(4),.scoring-dimension-table td:nth-child(5),.scoring-dimension-table td:nth-child(6),.scoring-dimension-table td:nth-child(7){white-space:nowrap}
.scoring-dimension-table tbody tr:hover{background:#fafbfc}
@media(max-width:900px){.scoring-dimension-heading{align-items:flex-start;flex-direction:column;gap:4px}.scoring-dimension-meta{white-space:normal}.scoring-dimension-table table{min-width:900px}}
@media print{.scoring-dimension-panel{break-inside:avoid;box-shadow:none}.scoring-dimension-table{overflow:visible}.scoring-dimension-table table{min-width:0;table-layout:auto;font-size:.72rem}.scoring-dimension-table th,.scoring-dimension-table td{width:auto!important;min-width:0!important;padding:6px 7px}}
"""
''',
)

text = replace_once(
    text,
    "<title>Metodologia de scoring - {escape(effective_version)}</title><link rel='stylesheet' href='css/site.css'></head>",
    "<title>Metodologia de scoring - {escape(effective_version)}</title><link rel='stylesheet' href='css/site.css'><style>{_SCORING_LAYOUT_CSS}</style></head>",
)

old_block = '''        blocks: list[str] = []
        for dimension, rows in grouped.items():
            body: list[str] = []
            for row in rows:
                factor = "-" if row["result_factor"] is None else f"{float(row['result_factor']):.2f}"
                effective = "-" if row["effective_contribution"] is None else f"{float(row['effective_contribution']):.3f}"
                group = str(row["scoring_group"] or "regra independente")
                rule_id = str(row["rule_id"])
                body.append(
                    "<tr>"
                    f"<td><strong>{escape(rule_id)}</strong></td>"
                    f"<td>{escape(_rule_description(rule_id))}</td>"
                    f"<td><code>{escape(group)}</code></td>"
                    f"<td>{float(row['weight']):g}</td>"
                    f"<td>{escape(str(row['result']))}</td>"
                    f"<td>{escape(factor)}</td>"
                    f"<td>{escape(effective)}</td>"
                    "</tr>"
                )
            label = _DIMENSION_LABELS.get(dimension, dimension)
            blocks.append(
                f"<article class='ref-card scoring-dimension-group'><h4>{escape(label)}</h4>"
                "<div class='table-wrap'><table><thead><tr>"
                "<th>Regra</th><th>Critério</th><th>Grupo</th><th>Peso</th><th>Resultado</th><th>Fator</th><th>Contribuição efetiva</th>"
                f"</tr></thead><tbody>{''.join(body)}</tbody></table></div></article>"
            )
        materialized = "<div class='grid scoring-weight-groups'>" + "".join(blocks) + "</div>" if blocks else "<p class='intro'>Nenhuma contribuição persistida disponível para detalhar pesos nesta projeção.</p>"
'''

new_block = '''        blocks: list[str] = []
        ordered_dimensions = [dimension for dimension in FEATURE_ORDER if dimension in grouped]
        ordered_dimensions.extend(dimension for dimension in grouped if dimension not in ordered_dimensions)
        for dimension in ordered_dimensions:
            rows = grouped[dimension]
            body: list[str] = []
            scoring_groups: set[str] = set()
            for row in rows:
                factor = "-" if row["result_factor"] is None else f"{float(row['result_factor']):.2f}"
                effective = "-" if row["effective_contribution"] is None else f"{float(row['effective_contribution']):.3f}"
                group = str(row["scoring_group"] or "regra independente")
                scoring_groups.add(group)
                rule_id = str(row["rule_id"])
                body.append(
                    "<tr>"
                    f"<td><strong>{escape(rule_id)}</strong></td>"
                    f"<td>{escape(_rule_description(rule_id))}</td>"
                    f"<td><code>{escape(group)}</code></td>"
                    f"<td>{float(row['weight']):g}</td>"
                    f"<td>{escape(str(row['result']))}</td>"
                    f"<td>{escape(factor)}</td>"
                    f"<td>{escape(effective)}</td>"
                    "</tr>"
                )
            label = _DIMENSION_LABELS.get(dimension, dimension)
            rule_label = "regra" if len(rows) == 1 else "regras"
            group_label = "grupo" if len(scoring_groups) == 1 else "grupos"
            blocks.append(
                "<article class='scoring-dimension-panel'>"
                f"<div class='scoring-dimension-heading'><h4>{escape(label)}</h4>"
                f"<span class='scoring-dimension-meta'>{len(rows)} {rule_label} · {len(scoring_groups)} {group_label}</span></div>"
                "<div class='table-wrap scoring-dimension-table'><table><thead><tr>"
                "<th>Regra</th><th>Critério</th><th>Grupo</th><th>Peso</th><th>Resultado</th><th>Fator</th><th>Contribuição efetiva</th>"
                f"</tr></thead><tbody>{''.join(body)}</tbody></table></div></article>"
            )
        materialized = "<div class='scoring-weight-groups'>" + "".join(blocks) + "</div>" if blocks else "<p class='intro'>Nenhuma contribuição persistida disponível para detalhar pesos nesta projeção.</p>"
'''
text = replace_once(text, old_block, new_block)

text = replace_once(
    text,
    "A organização abaixo evita repetir visualmente a dimensão em cada linha e mostra o critério humano da regra, o <code>scoring_group</code>, o peso, o fator efetivamente aplicado e a contribuição persistida.",
    "Cada dimensão ocupa um painel de largura total, mantendo regra, critério humano, <code>scoring_group</code>, peso, fator aplicado e contribuição persistida na mesma linha de leitura.",
)

TARGET.write_text(text, encoding='utf-8', newline='\n')

TEST.write_text(
    '''from pathlib import Path\n\n\ndef test_scoring_report_uses_full_width_dimension_panels() -> None:\n    source = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")\n    assert "class='grid scoring-weight-groups'" not in source\n    assert "class='scoring-weight-groups'" in source\n    assert "class='scoring-dimension-panel'" in source\n    assert "scoring-dimension-table" in source\n    assert "overflow-y:visible" in source\n    assert "max-height:none!important" in source\n    assert "min-width:940px" in source\n\n\ndef test_scoring_report_orders_dimension_panels_by_method_contract() -> None:\n    source = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")\n    assert "ordered_dimensions = [dimension for dimension in FEATURE_ORDER if dimension in grouped]" in source\n    assert "scoring_groups: set[str] = set()" in source\n    assert "scoring-dimension-meta" in source\n\n\ndef test_scoring_layout_is_page_scoped() -> None:\n    source = Path("src/rasai/score_geo_004_reporting.py").read_text(encoding="utf-8")\n    assert "<style>{_SCORING_LAYOUT_CSS}</style>" in source\n    report_site = Path("src/rasai/report_site.py").read_text(encoding="utf-8")\n    assert ".scoring-dimension-panel" not in report_site\n''',
    encoding='utf-8',
    newline='\n',
)

print('scoring report layout refinement applied')
