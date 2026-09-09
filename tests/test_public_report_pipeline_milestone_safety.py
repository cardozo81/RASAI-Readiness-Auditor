from __future__ import annotations

from pathlib import Path

import pytest

from rasai.public_report_safety import PublicReportSafetyError
from rasai.report_contract import REPORT_SURFACES
from rasai.report_semantics import enhance_report_html


_KNOWN_INTERNAL_PRESENTATION = (
    "M18/M20",
    "M21/M22",
    "M21 + M22 · domínio Web Performance",
    "M23 · domínio Web Performance",
    "Web Performance · M23",
    "M23 · metodologia",
    "Estado M23",
    "M24-CD-001",
    "Rastreamento e descoberta M24",
)

_PUBLIC_PAGE_NAMES = tuple(surface.filename for surface in REPORT_SURFACES) + (
    "consolidated.html",
)


@pytest.mark.parametrize("page_name", _PUBLIC_PAGE_NAMES)
def test_final_public_report_pipeline_removes_owned_internal_delivery_labels(
    tmp_path: Path,
    page_name: str,
) -> None:
    owned = " | ".join(_KNOWN_INTERNAL_PRESENTATION)
    source = (
        "<html><body><header><h1>RASAi</h1></header><main>"
        f"<section class='panel'><p>{owned}</p></section>"
        "</main></body></html>"
    )

    rendered = enhance_report_html(source, page_name=page_name, report_dir=tmp_path)

    for fragment in _KNOWN_INTERNAL_PRESENTATION:
        assert fragment not in rendered
    assert "CRAWLING-DISCOVERY-001" in rendered


@pytest.mark.parametrize("page_name", _PUBLIC_PAGE_NAMES)
def test_final_public_report_pipeline_rejects_unknown_internal_delivery_markup(
    tmp_path: Path,
    page_name: str,
) -> None:
    source = (
        "<html><body><header><h1>RASAi</h1></header><main>"
        "<section id='m42-internal-delivery'>conteúdo público</section>"
        "</main></body></html>"
    )

    with pytest.raises(PublicReportSafetyError, match="M42"):
        enhance_report_html(source, page_name=page_name, report_dir=tmp_path)


@pytest.mark.parametrize("page_name", _PUBLIC_PAGE_NAMES)
def test_final_public_report_pipeline_preserves_legitimate_audited_model_name(
    tmp_path: Path,
    page_name: str,
) -> None:
    evidence = "Produto M25 industrial observado na página auditada."
    source = (
        "<html><body><header><h1>RASAi</h1></header><main>"
        f"<section class='evidence'><p>{evidence}</p></section>"
        "</main></body></html>"
    )

    rendered = enhance_report_html(source, page_name=page_name, report_dir=tmp_path)

    assert evidence in rendered
