from __future__ import annotations

from html import escape
import json

from rasai.catalog_report_assurance import _credential_output_failures
from rasai.improvement_intelligence import _safe_ai_suggested_text, _validate_ai_payload
from rasai.secret_safety import detect_secret_exposures


def _cookie_finding() -> dict[str, object]:
    return {
        "finding_id": "PSF-COOKIE-AWSALB",
        "domain": "SECURITY",
        "severity": "MEDIUM",
        "source": "PASSIVE_SECURITY",
        "title": "Cookie definido sem Secure em contexto HTTPS",
        "observation": "O cookie AWSALB foi observado sem o atributo Secure.",
        "evidence_ids": ["EV-COOKIE"],
        "impacts": {"security": 2},
        "details": {
            "category": "Cookies",
            "target": {
                "kind": "COOKIE",
                "label": "AWSALB",
                "ref": "CK-AWSALB",
                "owner_class": "TARGET_SITE",
            },
            "deterministic_remediation": (
                "Adicionar Secure quando o cookie for destinado a contexto HTTPS, "
                "preservando os demais atributos necessários."
            ),
        },
    }


def test_cookie_suggested_text_does_not_materialize_set_cookie_name_value() -> None:
    payload = {
        "summary": "Correção de cookie.",
        "recommendations": [
            {
                "finding_id": "PSF-COOKIE-AWSALB",
                "evidence_ids": ["EV-COOKIE"],
                "confidence": 0.95,
                "effort": "LOW",
                "title": "Adicionar Secure ao cookie AWSALB",
                "recommendation": "Adicionar o atributo Secure ao cookie observado.",
                "current_degradation": "O cookie foi observado sem Secure em HTTPS.",
                "expected_benefit": "Reduzir exposição do cookie a transporte incompatível.",
                "rationale": "A alteração deve ser feita na emissão do cookie.",
                "suggested_text": (
                    "Configuração de resposta: "
                    "`Set-Cookie: AWSALB=[valor]; Secure; [demais atributos atuais]`"
                ),
                "verification": "Reauditar e confirmar o atributo Secure.",
            }
        ],
    }

    _summary, recommendations = _validate_ai_payload(payload, [_cookie_finding()], 1)
    suggested = str(recommendations[0]["suggested_text"])

    assert "Set-Cookie:" not in suggested
    assert "AWSALB=" not in suggested
    assert "cookie AWSALB" in suggested
    assert "Adicionar Secure" in suggested
    assert not detect_secret_exposures(
        suggested,
        path="issue-58-safe-guidance",
        strict=True,
    )
    assert _credential_output_failures(
        "<div>" + escape(suggested) + "</div>"
    ) == []


def test_cookie_assurance_still_rejects_raw_set_cookie_assignment() -> None:
    failures = _credential_output_failures(
        "<div>Set-Cookie: AWSALB=[valor]; Secure; Path=/</div>"
    )
    assert failures == ["padrão de credencial detectado no HTML"]



def test_legacy_persisted_cookie_details_json_is_sanitized_for_read_only_projection() -> None:
    legacy_finding = {
        "finding_id": "PSF-COOKIE-AWSALB",
        "details_json": json.dumps(_cookie_finding()["details"], ensure_ascii=False),
    }
    raw = "Set-Cookie: AWSALB=[valor]; Secure; Path=/"

    suggested = _safe_ai_suggested_text(raw, legacy_finding)

    assert suggested is not None
    assert "Set-Cookie:" not in suggested
    assert "AWSALB=" not in suggested
    assert "cookie AWSALB" in suggested
    assert "Adicionar Secure" in suggested
    assert _credential_output_failures(
        "<div>" + escape(str(suggested)) + "</div>"
    ) == []


def test_non_cookie_suggested_text_is_unchanged() -> None:
    finding = {
        "finding_id": "HTML:IMG_DIMENSIONS",
        "domain": "TECHNICAL_HTML",
        "severity": "MEDIUM",
        "source": "HTML_STRUCTURE",
        "title": "Imagem sem dimensões",
        "observation": "Dimensões não observadas.",
        "evidence_ids": ["HTML:STRUCTURE"],
        "impacts": {"performance": 2},
        "details": {},
    }
    payload = {
        "summary": "Correção HTML.",
        "recommendations": [
            {
                "finding_id": "HTML:IMG_DIMENSIONS",
                "evidence_ids": ["HTML:STRUCTURE"],
                "confidence": 0.9,
                "effort": "LOW",
                "title": "Declarar dimensões",
                "recommendation": "Adicionar width e height.",
                "current_degradation": "A imagem não declara dimensões.",
                "expected_benefit": "Reduzir instabilidade de layout.",
                "rationale": "Reserva antecipadamente o espaço de renderização.",
                "suggested_text": "Adicionar width e height coerentes com o asset.",
                "verification": "Reauditar o HTML e comparar CLS.",
            }
        ],
    }

    _summary, recommendations = _validate_ai_payload(payload, [finding], 1)
    assert (
        recommendations[0]["suggested_text"]
        == "Adicionar width e height coerentes com o asset."
    )
