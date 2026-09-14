"""Test bootstrap for the current, unpublished RASAi product contract.

The executable entrypoints compose specialist consumers, public report presentation and
optional-work reconciliation before any audit is processed. Tests import many low-level
modules directly, so install the same current product layers here before test module
collection. This is the only product contract under development; there is no published
compatibility mode to preserve.
"""
from rasai.ai_orchestration_unification import install_ai_orchestration_unification
from rasai.gsc_oauth_console import install as install_gsc_oauth_console
from rasai.gsc_oauth_runtime import install as install_gsc_oauth_runtime
from rasai.report_public_ux_guard import install as install_report_public_ux_guard
from rasai.selective_optional_reprocess import install as install_selective_optional_reprocess


install_ai_orchestration_unification()
install_gsc_oauth_runtime()
install_gsc_oauth_console()
install_selective_optional_reprocess()
install_report_public_ux_guard()
