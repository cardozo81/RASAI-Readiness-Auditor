"""Risk-oriented tests for M4 - Extraction + Evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rasai.domain import Audit, DeviceContext, Page, PageSnapshot, new_id
from rasai.extraction import ContentExtractor
from rasai.m3 import M3ExecutionResult
from rasai.m4 import execute_m4
from rasai.persistence import AuditPersistence, AuditWorkspace


_HTML = """<!doctype html>
<html>
<head>
  <title>Produto Alpha</title>
  <meta name="description" content="Descrição clara">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="https://example.test/produto">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Alpha"}</script>
  <script type="application/ld+json">{"broken":</script>
</head>
<body>
  <header>Boilerplate header</header>
  <nav><a href="/nav">Navigation</a></nav>
  <main>
    <h1>Produto Alpha</h1>
    <p>Conteúdo principal com preço R$ 10,00 e contexto preservado.</p>
    <a href="/comprar" rel="nofollow">Comprar agora</a>
  </main>
  <footer>Boilerplate footer</footer>
</body>
</html>
"""


class M4ExtractionEvidenceTests(unittest.TestCase):
    def test_extractor_preserves_structural_signals_and_invalid_jsonld(self) -> None:
        result = ContentExtractor().extract(_HTML)

        self.assertEqual(result.title, "Produto Alpha")
        self.assertEqual(result.description, "Descrição clara")
        self.assertEqual(result.canonical, "https://example.test/produto")
        self.assertEqual(result.meta_robots, "index,follow")
        self.assertEqual([(item.level, item.text) for item in result.headings], [(1, "Produto Alpha")])
        self.assertIn("Conteúdo principal", result.main_content)
        self.assertNotIn("Boilerplate header", result.main_content)
        self.assertEqual(result.main_content_source, "MAIN_OR_ARTICLE")
        self.assertIn("/comprar", [item.href for item in result.links])
        self.assertEqual(len(result.structured_data), 2)
        self.assertEqual(result.structured_data[0].types, ("Product",))
        self.assertIsNone(result.structured_data[0].parse_error)
        self.assertEqual(result.structured_data[1].parse_error, "INVALID_JSON")

    def test_execute_m4_updates_each_device_and_persists_reopenable_evidence(self) -> None:
        captured_at = datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc)
        audit = Audit(audit_id=new_id("AUD"), project_name="M4 test")
        page = Page(
            page_id=new_id("PGE"),
            audit_id=audit.audit_id,
            normalized_url="https://example.test/produto",
            discovered_url="https://example.test/produto",
        )

        with TemporaryDirectory() as temp_dir:
            workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
            raw_dir = workspace.artifacts / "raw"
            raw_dir.mkdir(parents=True)
            raw_path = raw_dir / "response.html"
            raw_path.write_text("<html><body>raw shell</body></html>", encoding="utf-8")
            raw_ref = raw_path.relative_to(workspace.root).as_posix()

            rendered_refs: dict[DeviceContext, str] = {}
            snapshots: dict[DeviceContext, PageSnapshot] = {}
            for device in (DeviceContext.DESKTOP, DeviceContext.MOBILE):
                rendered_dir = workspace.artifacts / "rendered" / device.value.lower()
                rendered_dir.mkdir(parents=True)
                rendered_path = rendered_dir / "rendered.html"
                rendered_path.write_text(_HTML.replace("Produto Alpha", f"Produto {device.value}"), encoding="utf-8")
                rendered_ref = rendered_path.relative_to(workspace.root).as_posix()
                rendered_refs[device] = rendered_ref
                snapshots[device] = PageSnapshot(
                    snapshot_id=new_id("SNP"),
                    page_id=page.page_id,
                    device=device,
                    requested_url=page.normalized_url,
                    final_url=page.normalized_url,
                    captured_at=captured_at,
                    http_status=200,
                    content_type="text/html",
                    raw_artifact_ref=raw_ref,
                    rendered_artifact_ref=rendered_ref,
                )

            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(audit)
                persistence.pages.add(page)
                for snapshot in snapshots.values():
                    persistence.snapshots.add(snapshot)

                m3_result = M3ExecutionResult(
                    snapshot_ids={
                        page.page_id: {
                            device: snapshot.snapshot_id for device, snapshot in snapshots.items()
                        }
                    },
                    failures=(),
                )
                result = execute_m4(m3_result, persistence, workspace)

                self.assertEqual(result.failures, ())
                self.assertEqual(set(result.evidence_ids), {item.snapshot_id for item in snapshots.values()})
                for device, original in snapshots.items():
                    updated = persistence.snapshots.get(original.snapshot_id)
                    self.assertIsNotNone(updated)
                    self.assertEqual(updated.device, device)
                    self.assertEqual(updated.title, f"Produto {device.value}")
                    self.assertIsNotNone(updated.main_content_ref)
                    self.assertIsNotNone(updated.structured_data_ref)
                    self.assertTrue((workspace.root / updated.main_content_ref).is_file())
                    structured_payload = json.loads((workspace.root / updated.structured_data_ref).read_text(encoding="utf-8"))
                    self.assertEqual(len(structured_payload["blocks"]), 2)
                    ids = result.evidence_ids[original.snapshot_id]
                    self.assertGreaterEqual(len(ids), 7)
                    for evidence_id in ids:
                        evidence = persistence.evidence.get(evidence_id)
                        self.assertIsNotNone(evidence)
                        self.assertEqual(evidence.snapshot_id, original.snapshot_id)
                        self.assertEqual(evidence.device, device)

            with AuditPersistence(AuditWorkspace.open(workspace.root)) as reopened:
                for original in snapshots.values():
                    updated = reopened.snapshots.get(original.snapshot_id)
                    self.assertIsNotNone(updated.main_content_ref)
                    self.assertTrue((workspace.root / updated.main_content_ref).is_file())

    def test_missing_artifact_is_localized_and_other_snapshot_continues(self) -> None:
        captured_at = datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc)
        audit = Audit(audit_id=new_id("AUD"), project_name="M4 isolation")
        page = Page(
            page_id=new_id("PGE"),
            audit_id=audit.audit_id,
            normalized_url="https://example.test/",
            discovered_url="https://example.test/",
        )

        with TemporaryDirectory() as temp_dir:
            workspace = AuditWorkspace.create(Path(temp_dir), audit.audit_id)
            rendered = workspace.artifacts / "mobile.html"
            rendered.write_text(_HTML, encoding="utf-8")
            desktop = PageSnapshot(
                snapshot_id=new_id("SNP"), page_id=page.page_id, device=DeviceContext.DESKTOP,
                requested_url=page.normalized_url, final_url=page.normalized_url, captured_at=captured_at,
            )
            mobile = PageSnapshot(
                snapshot_id=new_id("SNP"), page_id=page.page_id, device=DeviceContext.MOBILE,
                requested_url=page.normalized_url, final_url=page.normalized_url, captured_at=captured_at,
                rendered_artifact_ref=rendered.relative_to(workspace.root).as_posix(),
            )

            with AuditPersistence(workspace) as persistence:
                persistence.audits.add(audit)
                persistence.pages.add(page)
                persistence.snapshots.add(desktop)
                persistence.snapshots.add(mobile)
                result = execute_m4(
                    M3ExecutionResult(
                        snapshot_ids={page.page_id: {DeviceContext.DESKTOP: desktop.snapshot_id, DeviceContext.MOBILE: mobile.snapshot_id}},
                        failures=(),
                    ),
                    persistence,
                    workspace,
                )

                self.assertEqual(len(result.failures), 1)
                self.assertEqual(result.failures[0].snapshot_id, desktop.snapshot_id)
                self.assertEqual(result.failures[0].error_kind, "EXTRACTION_INPUT_UNAVAILABLE")
                self.assertEqual(result.evidence_ids[desktop.snapshot_id], ())
                self.assertGreater(len(result.evidence_ids[mobile.snapshot_id]), 0)
                self.assertEqual(persistence.snapshots.get(mobile.snapshot_id).title, "Produto Alpha")


if __name__ == "__main__":
    unittest.main()
