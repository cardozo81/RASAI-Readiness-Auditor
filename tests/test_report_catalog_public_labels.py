from __future__ import annotations

from types import SimpleNamespace

from rasai.catalog_report_public_labels import public_label
from rasai.catalog_report_presentation import (
    _kv,
    _rich_text,
    _status_label,
    _table,
    _temporal_mode_label,
)
from rasai.semantic import semantic_output_language_directive


def test_internal_contract_values_have_human_labels() -> None:
    expected = {
        "DIRECT_PUBLIC_INDEX_API": "API pública de índice",
        "DIRECT_OFFICIAL_API": "API oficial da fonte",
        "DETERMINISTIC-CORRELATIONAL-001": "Correlação determinística de evidências",
        "LIVE_RECOLLECTION": "Coleta ao vivo desta auditoria",
        "REUSED_EVIDENCE": "Evidência reutilizada",
        "REPLAY_SAFE": "Reutilizável sem nova coleta",
        "CONTENT_COMPARISON_DISABLED": "Comparação de conteúdo desabilitada",
        "CLASSIFICATION_ONLY": "Somente classificação",
        "UNKNOWN_ACTION": "Ação não classificada",
        "RATE_LIMITED": "Limite de requisições atingido",
        "NON_SCORING": "Não participa da pontuação",
    }
    for raw, label in expected.items():
        assert public_label(raw) == label


def test_table_and_kv_humanize_internal_values_but_keep_tooltip() -> None:
    table = _table(
        ("Método", "Estado"),
        [("DIRECT_OFFICIAL_API", "RATE_LIMITED")],
    )
    kv = _kv((("Metodologia", "DETERMINISTIC-CORRELATIONAL-001"),))
    assert "API oficial da fonte" in table
    assert "Limite de requisições atingido" in table
    assert "title='DIRECT_OFFICIAL_API'" in table
    assert "title='RATE_LIMITED'" in table
    assert "Correlação determinística de evidências" in kv
    assert "title='DETERMINISTIC-CORRELATIONAL-001'" in kv


def test_status_label_uses_human_contract_label() -> None:
    assert _status_label("CONTENT_COMPARISON_DISABLED") == "Comparação de conteúdo desabilitada"
    assert _status_label("SERP_OBSERVATION_UNAVAILABLE") == "Observação de SERP indisponível"


def test_temporal_mode_is_human_first_and_preserves_internal_token() -> None:
    rendered = str(_temporal_mode_label("LIVE_RECOLLECTION"))
    assert "Coleta ao vivo desta auditoria" in rendered
    assert "title='LIVE_RECOLLECTION'" in rendered


def test_rich_text_renders_safe_external_links_in_new_tab() -> None:
    rendered = str(
        _rich_text(
            "Veja [documentação oficial](https://developers.google.com/search/docs) e `sameAs`."
        )
    )
    assert "target='_blank'" in rendered
    assert "rel='noopener noreferrer'" in rendered
    assert "documentação oficial ↗" in rendered
    assert "<code>sameAs</code>" in rendered
    assert "[documentação oficial]" not in rendered


def test_rich_text_escapes_arbitrary_html() -> None:
    rendered = str(_rich_text("<script>alert(1)</script> https://example.test/a"))
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "href='https://example.test/a'" in rendered


def test_report_placeholder_uses_hyphen_not_em_dash() -> None:
    rendered = _table(("Valor",), [("—",)])
    assert "<td>-</td>" in rendered
    assert "—" not in rendered


def test_semantic_output_language_directive_uses_audit_language() -> None:
    directive = semantic_output_language_directive(SimpleNamespace(primary_language="pt-BR"))
    assert "pt-BR" in directive
    assert "reasoning_summary" in directive
    assert "observed_value.summary" in directive
    assert "primary_intent" in directive
