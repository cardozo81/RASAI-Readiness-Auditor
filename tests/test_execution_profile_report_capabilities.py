from rasai.execution_profile_report_capabilities import _profile_metrics


def test_execution_evidence_uses_capability_terminology() -> None:
    rendered = _profile_metrics(
        {
            "execution_profile": {
                "profile_id": "performance",
                "label": "Performance",
                "capabilities": ["web-performance"],
                "ai_mode": "off",
                "manual_overrides": [],
            }
        }
    )

    assert "Capacidades do perfil" in rendered
    assert "web-performance" in rendered
    assert "Módulos do perfil" not in rendered
