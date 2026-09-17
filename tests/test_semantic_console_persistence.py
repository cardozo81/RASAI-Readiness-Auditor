from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import os
from unittest.mock import patch

from rasai.console_m23 import State
from rasai.console_settings import load_console_config, save_console_config
from rasai.property_semantic_profile import PROPERTY_SEMANTIC_PROFILE_ENV_NAMES
from rasai.semantic_context_console import install as install_semantic_context_console


_CONTENT_NAMES = (
    "RASAI_CONTENT_RISK_PROFILE",
    "RASAI_YMYL_CATEGORY",
    "RASAI_PAGE_PURPOSE",
    "RASAI_INTENDED_AUDIENCE",
    "RASAI_EXPERIENCE_REQUIREMENT",
    "RASAI_FRESHNESS_SENSITIVITY",
    "RASAI_CONTENT_ORIGIN",
)


def test_semantic_context_round_trips_through_console_ini() -> None:
    install_semantic_context_console()
    values = {
        "RASAI_PROPERTY_BUSINESS_SECTOR": "Software B2B",
        "RASAI_PROPERTY_BUSINESS_DESCRIPTION": "Plataforma financeira empresarial",
        "RASAI_PROPERTY_PRIMARY_OFFERING": "SaaS financeiro",
        "RASAI_PROPERTY_TARGET_AUDIENCE_PROFILE": "CFOs de PMEs brasileiras",
        "RASAI_PROPERTY_PRIMARY_GOAL": "Gerar demonstrações",
        "RASAI_PROPERTY_POSITIONING": "Menos complexidade financeira",
        "RASAI_CONTENT_RISK_PROFILE": "standard",
        "RASAI_YMYL_CATEGORY": "none",
        "RASAI_PAGE_PURPOSE": "product-service",
        "RASAI_INTENDED_AUDIENCE": "professional",
        "RASAI_EXPERIENCE_REQUIREMENT": "beneficial",
        "RASAI_FRESHNESS_SENSITIVITY": "medium",
        "RASAI_CONTENT_ORIGIN": "first-party",
    }
    names = (*PROPERTY_SEMANTIC_PROFILE_ENV_NAMES, *_CONTENT_NAMES)

    with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
        for name in names:
            os.environ.pop(name, None)
        os.environ.update(values)
        path = Path(directory) / "semantic.ini"
        save_console_config(State(), path)

        text = path.read_text(encoding="utf-8")
        for name, value in values.items():
            assert f"{name} = {value}" in text

        for name in names:
            os.environ.pop(name, None)
        result = load_console_config(State(), path)
        assert result.warnings == ()
        for name, value in values.items():
            assert os.environ.get(name) == value
