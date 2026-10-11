"""#377: small public-copy regressions; engine IDs remain unchanged in code/data."""
from pathlib import Path
import re

from rasai.dynatrace_apdex_arch_advisory_355 import explain_dynatrace_apdex_pt_br
from rasai.cat07_architecture_reporting_358 import _REASON_LABELS


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
        "cat07_architecture_reporting_358.py": (
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
