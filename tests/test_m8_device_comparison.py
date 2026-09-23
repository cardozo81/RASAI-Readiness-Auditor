"""Risk-oriented tests for M8 - Desktop × Mobile comparison."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.comparison import DeviceComparator, DeviceComparisonOutcome
from rasai.domain import DeviceContext, PageSnapshot, RuleResult


_NOW = datetime(2026, 9, 2, 17, 0, tzinfo=timezone.utc)


class DeviceComparatorTests(unittest.TestCase):
    def _snapshot(self, device: DeviceContext, *, status: int = 200, canonical: str = "https://example.test/p", rendered_ref: str | None = None) -> PageSnapshot:
        return PageSnapshot(
            snapshot_id=f"SNP-{device.value}",
            page_id="PGE-1",
            device=device,
            requested_url="https://example.test/p",
            final_url="https://example.test/p",
            captured_at=_NOW,
            http_status=status,
            title="Produto",
            canonical=canonical,
            meta_robots="index,follow",
            rendered_artifact_ref=rendered_ref,
        )

    def test_benign_difference_is_classified_but_not_material(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "desktop.html").write_text("<main><h1>Produto</h1><a href='/a'>A</a></main>", encoding="utf-8")
            (root / "mobile.html").write_text("<main><h1>Produto</h1><a href='/menu'>Menu</a></main>", encoding="utf-8")
            comparison = DeviceComparator().compare(
                desktop=self._snapshot(DeviceContext.DESKTOP, rendered_ref="desktop.html"),
                mobile=self._snapshot(DeviceContext.MOBILE, rendered_ref="mobile.html"),
                workspace_root=root,
            )
            self.assertEqual(comparison.outcome, DeviceComparisonOutcome.DIFFERENT)
            self.assertIn("links", comparison.changed_fields)
            self.assertFalse(comparison.materially_problematic)

    def test_indexability_or_http_access_difference_is_material(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            html = "<main>Conteúdo</main>"
            (root / "d.html").write_text(html, encoding="utf-8")
            (root / "m.html").write_text(html, encoding="utf-8")
            comparison = DeviceComparator().compare(
                desktop=self._snapshot(DeviceContext.DESKTOP, status=200, canonical="https://example.test/p", rendered_ref="d.html"),
                mobile=self._snapshot(DeviceContext.MOBILE, status=500, canonical="https://example.test/mobile", rendered_ref="m.html"),
                workspace_root=root,
            )
            self.assertEqual(comparison.outcome, DeviceComparisonOutcome.DIFFERENT)
            self.assertIn("http_status", comparison.material_fields)
            self.assertIn("canonical", comparison.material_fields)

    def test_missing_device_is_unknown_not_fail(self) -> None:
        comparison = DeviceComparator().compare(
            desktop=self._snapshot(DeviceContext.DESKTOP),
            mobile=None,
            workspace_root=Path("."),
        )
        self.assertEqual(comparison.outcome, DeviceComparisonOutcome.UNKNOWN)
        self.assertFalse(comparison.materially_problematic)


if __name__ == "__main__":
    unittest.main()
