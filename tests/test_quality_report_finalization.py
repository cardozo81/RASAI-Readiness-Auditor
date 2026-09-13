from __future__ import annotations

import inspect

from rasai import report_completion


def _module_source() -> str:
    """Read the canonical implementation, independent of runtime-installed wrappers."""
    return inspect.getsource(report_completion)


def test_final_report_pipeline_materializes_audit_quality_before_public_polish() -> None:
    source = _module_source()
    quality = source.index('run("audit-quality"')
    consistency = source.index('run("consistency"')
    public_quality = source.index('"public-report-quality"')
    finalizer = source.index('"presentation-finalizer"')
    manifest = source.index('run("manifest"')

    assert "from rasai.quality.reporting import write_quality_report" in source
    assert "write_quality_report(workspace.root)" in source
    assert quality < consistency < public_quality < finalizer < manifest


def test_audit_quality_is_read_only_and_does_not_replace_multi_audit_flows() -> None:
    source = _module_source()
    assert "write_verification_report" not in source
    assert "write_timeline_report" not in source
