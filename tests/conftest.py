"""Test bootstrap for the current, unpublished RASAi product contract.

The executable entrypoints compose specialist consumers onto the canonical AI runtime
before any audit is processed. Tests import many low-level modules directly, so install
the same provider-selection and optional-work reconciliation layers here before test
module collection. This is the only product contract under development; there is no
published compatibility mode to preserve.
"""
from rasai.ai_orchestration_unification import install_ai_orchestration_unification
from rasai.selective_optional_reprocess import install as install_selective_optional_reprocess


install_ai_orchestration_unification()
install_selective_optional_reprocess()
