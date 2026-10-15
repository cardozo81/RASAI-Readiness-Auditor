"""#377: small public-copy regressions; engine IDs remain unchanged in code/data."""
from pathlib import Path
import re

from rasai.dynatrace_apdex_arch_advisory import explain_dynatrace_apdex_pt_br
from rasai.cat07_architecture_reporting import _REASON_LABELS


ROOT = Path(__file__).resolve().parents[1] / "src" / "rasai"
_INTERNAL = re.compile(r"(?<!\w)M\d{1,2}(?:/M\d{1,2})?(?!\w)")


def test_known_console_and_metrics_public_copy_is_functional_not_module_codes():
    cases = {
        "console_search_intelligence.py": (
            "Tempo e consumo das análises por IA:",
            "Cronologia IA M18/M20:",
        ),
        "console_apdex_configuration.py": (
            "a arquitetura será identificada durante a coleta",
            "a classificação M6 será descoberta depois da coleta",
        ),
        "catalog_report_site.py": (
            "São durações das solicitações de análise por IA",
            "São durações por tentativa nas bases M18/M20",
        ),
        "cat07_architecture_reporting.py": (
            "Rastreabilidade da arquitetura identificada",
            "Rastreabilidade da arquitetura M6",
        ),
    }
    for name, (friendly, obsolete) in cases.items():
        text = (ROOT / name).read_text(encoding="utf-8")
        assert friendly in text, name
        assert obsolete not in text, name


def test_cat07_reason_labels_have_no_raw_internal_module_refs():
    labels = " | ".join(_REASON_LABELS.values())
    assert not _INTERNAL.search(labels)


def test_dynatrace_human_explanation_omits_internal_module_tokens():
    message = explain_dynatrace_apdex_pt_br({
        "status": "INSUFFICIENT_ACTION_SCOPE",
        "architecture": "CSR_SPA",
        "observed_kpm": {"load_actions": "USER_ACTION_DURATION"},
        "reasons": ["XHR_APDEX_CONFIGURATION_NOT_PROVIDED"],
        "review_actions": [],
    })
    rendered = str(message)
    assert not _INTERNAL.search(rendered)
    assert "índices sintéticos de navegação e experiência" in rendered
    assert "Configuração de Apdex XHR não fornecida" in rendered
    assert "mesma amostra" in rendered


def test_audit_timing_inspector_explains_ia_http_without_internal_module_names(capsys):
    from rasai.audit_attempt_inspection_319 import main
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    rendered = capsys.readouterr().out
    assert "tentativas de IA" in rendered
    assert "requisições HTTP" in rendered
    assert "M18/M20" not in rendered
    assert "M21" not in rendered
    inspector = (ROOT / "audit_attempt_inspection_319.py").read_text(encoding="utf-8")
    assert "O recorte usa somente relógios das tentativas de análise" in inspector
    assert "Os tempos informados são somas verificadas" in inspector
    assert "Valores M21 são somas" not in inspector


def test_console_cost_operator_guide_has_human_names():
    doc = (ROOT.parents[1] / "docs" / "CONSOLE_COST_AND_USAGE.md").read_text(encoding="utf-8")
    assert "Inspeção de tempos das análises por IA e requisições web" in doc
    assert "Inspeção read-only de tempos M18/M20" not in doc
    assert "cronologia de tentativas IA M18/M20" not in doc
    assert "observed_http_request_sums_ms" in doc  # technical field stays stable
