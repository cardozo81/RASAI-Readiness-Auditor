"""Canonical Synthetic Apdex concurrency and load guardrails.

This module centralizes public concurrency limits, pacing requirements and
operator-facing risk labels for both synthetic Apdex collectors.
"""
from __future__ import annotations

NAVIGATION_MAX_CONCURRENCY = 4
EXPERIENCE_MAX_CONCURRENCY = 3
ADVANCED_MIN_DELAY_SECONDS = 1.0


def navigation_risk(concurrency: int) -> str:
    if concurrency <= 1:
        return "BAIXO / RECOMENDADO"
    if concurrency == 2:
        return "BAIXO A MODERADO"
    if concurrency == 3:
        return "MODERADO"
    return "ALTO / AVANÇADO"


def experience_risk(concurrency: int) -> str:
    if concurrency <= 1:
        return "BAIXO / RECOMENDADO"
    if concurrency == 2:
        return "MODERADO"
    return "ALTO / AVANÇADO"


def validate_navigation_concurrency(concurrency: int, delay_seconds: float) -> None:
    if concurrency < 1 or concurrency > NAVIGATION_MAX_CONCURRENCY:
        raise ValueError(
            f"concurrency deve estar entre 1 e {NAVIGATION_MAX_CONCURRENCY}"
        )
    if concurrency >= 3 and delay_seconds < ADVANCED_MIN_DELAY_SECONDS:
        raise ValueError(
            f"concurrency {concurrency} exige delay_seconds >= "
            f"{ADVANCED_MIN_DELAY_SECONDS:g} para limitar a pressão sobre o alvo"
        )


def validate_experience_concurrency(concurrency: int, delay_seconds: float) -> None:
    if concurrency < 1 or concurrency > EXPERIENCE_MAX_CONCURRENCY:
        raise ValueError(
            "Synthetic User Experience Apdex: concurrency deve estar entre "
            f"1 e {EXPERIENCE_MAX_CONCURRENCY}"
        )
    if concurrency >= 3 and delay_seconds < ADVANCED_MIN_DELAY_SECONDS:
        raise ValueError(
            "Synthetic User Experience Apdex: concurrency 3 exige "
            f"delay_seconds >= {ADVANCED_MIN_DELAY_SECONDS:g}"
        )
