from __future__ import annotations

from rasai.content_value import _evaluate, _signals
from rasai.domain import RuleResult


def test_content_value_differentiation_is_unknown_without_explicit_evidence() -> None:
    text = (
        "Este guia explica o processo com detalhes suficientes para orientar a implementação. "
        * 20
    )
    evaluation = _evaluate(_signals(text))
    assert evaluation["BR-GEO-058"][0] == RuleResult.UNKNOWN


def test_content_value_can_recognize_explicit_first_party_signal() -> None:
    text = (
        "Nossa pesquisa mediu o comportamento em uma amostra própria. "
        "Analisamos os resultados e descrevemos a metodologia utilizada. "
        * 15
    )
    evaluation = _evaluate(_signals(text))
    assert evaluation["BR-GEO-058"][0] == RuleResult.PASS


def test_content_value_missing_input_never_becomes_fail() -> None:
    evaluation = _evaluate(_signals(""))
    assert all(item[0] != RuleResult.FAIL for item in evaluation.values())
    assert evaluation["BR-GEO-057"][0] == RuleResult.UNKNOWN
    assert evaluation["BR-GEO-059"][0] == RuleResult.UNKNOWN
