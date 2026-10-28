from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from rasai.consolidation.cons5 import (
    LONGITUDINAL_CONTRACT,
    MATERIALIZATION_CONTRACT,
    REPORT_FORMAT_VERSION,
    find_existing,
    materialize,
    request_fingerprint,
)
from rasai.consolidation.models import ConsolidationFilter, GenerationResult, RefreshResult


class Cons5MaterializationTests(unittest.TestCase):
    def test_reused_base_renderer_is_cloned_without_rewriting_source_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base_dir = root / "consolidated" / "CONS-BASE-TEST"
            base_dir.mkdir(parents=True)
            report = base_dir / "report.html"
            manifest = base_dir / "manifest.json"
            report.write_text(
                "<html><section id='apdex'><p>base</p></section>"
                "<footer>Gerado em x · formato CONS-3 · fingerprint base</footer></html>",
                encoding="utf-8",
            )
            manifest.write_text(json.dumps({
                "cons_id": "CONS-BASE-TEST",
                "report_format_version": "CONS-3",
                "request_fingerprint": "base",
                "source_fingerprint": "source",
                "aggregation_policy": {},
            }), encoding="utf-8")
            report_before = report.read_bytes()
            manifest_before = manifest.read_bytes()
            refresh = RefreshResult(1, 0, 1, 0, ())
            base = GenerationResult(base_dir, report, manifest, True, "base", refresh)

            result = materialize(
                audits_root=root,
                base_result=base,
                source_fingerprint="source",
                filters=ConsolidationFilter(),
                series=(),
            )

            self.assertNotEqual(result.report_dir, base_dir)
            self.assertEqual(report.read_bytes(), report_before)
            self.assertEqual(manifest.read_bytes(), manifest_before)
            payload = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["report_format_version"], REPORT_FORMAT_VERSION)
            self.assertEqual(payload["materialization_contract"], MATERIALIZATION_CONTRACT)
            self.assertEqual(payload["request_fingerprint"], result.request_fingerprint)
            self.assertEqual(payload["temporal_apdex"]["contract"], "TEMPORAL-APDEX-001")
            self.assertEqual(payload["temporal_apdex"]["base_request_fingerprint"], "base")
            self.assertNotIn("legacy_request_fingerprint", payload["temporal_apdex"])
            self.assertIn("formato CONS-5", result.report_path.read_text(encoding="utf-8"))

            # A clonagem intermediária ainda não é um snapshot final reutilizável:
            # faltam decisão, governança e hashes do pacote, aplicados pelo serviço depois.
            self.assertIsNone(find_existing(root, result.request_fingerprint, refresh))
            payload["longitudinal_analysis"] = {
                "contract": LONGITUDINAL_CONTRACT,
                "ai_status": "COMPLETE",
            }
            result.manifest_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(find_existing(root, result.request_fingerprint, refresh))

    def test_new_base_is_materialized_as_cons5(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "consolidated" / "CONS-NEW"
            output.mkdir(parents=True)
            report = output / "report.html"
            manifest = output / "manifest.json"
            report.write_text(
                "<html><section id='apdex'><p>base</p></section>"
                "<footer>Gerado em x · formato CONS-3 · fingerprint base</footer></html>",
                encoding="utf-8",
            )
            manifest.write_text(json.dumps({
                "cons_id": "CONS-NEW",
                "report_format_version": "CONS-3",
                "request_fingerprint": "base",
                "source_fingerprint": "source",
                "aggregation_policy": {},
            }), encoding="utf-8")
            base = GenerationResult(output, report, manifest, False, "base", RefreshResult(1, 1, 0, 0, ()))
            result = materialize(
                audits_root=root,
                base_result=base,
                source_fingerprint="source",
                filters=ConsolidationFilter(),
                series=(),
            )
            self.assertEqual(result.report_dir, output)
            self.assertIn("formato CONS-5", report.read_text(encoding="utf-8"))
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["report_format_version"], "CONS-5")
            self.assertEqual(payload["materialization_contract"], MATERIALIZATION_CONTRACT)
            self.assertEqual(payload["temporal_apdex"]["base_request_fingerprint"], "base")

    def test_find_existing_rejects_tampered_package_and_preserves_source_files(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "consolidated" / "CONS-INTEGRITY-TEST"
            output.mkdir(parents=True)
            required = (
                "report.html",
                "decision-context.json",
                "longitudinal-evidence.json",
                "execution.json",
            )
            for name in required:
                (output / name).write_text(
                    "<html>relatório sintético</html>" if name == "report.html" else "{}",
                    encoding="utf-8",
                )
            fingerprint = request_fingerprint("source", ConsolidationFilter())
            payload = {
                "report_format_version": REPORT_FORMAT_VERSION,
                "request_fingerprint": fingerprint,
                "materialization_contract": MATERIALIZATION_CONTRACT,
                "temporal_apdex": {"contract": "TEMPORAL-APDEX-001"},
                "longitudinal_analysis": {
                    "contract": LONGITUDINAL_CONTRACT,
                    "catalog_contract": "CONSOLIDATED-CATALOG-LONGITUDINAL-006",
                    "ai_status": "NOT_REQUESTED",
                },
                "source_governance": {"contract": "CONSOLIDATED-SOURCE-GOVERNANCE-003"},
                "decision_context": {"contract": "CONSOLIDATED-DECISION-CONTEXT-002"},
                "specialist_ai": {"requested": False},
                "package_integrity": {
                    "files": {
                        name: {"sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
                        for name in required
                    }
                },
            }
            (output / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
            refresh = RefreshResult(1, 0, 1, 0, ())
            initial = find_existing(root, fingerprint, refresh)
            self.assertIsNotNone(initial)
            self.assertTrue(initial.reused)
            baseline = {name: (output / name).read_bytes() for name in required}
            original_manifest = (output / "manifest.json").read_bytes()
            for name in required:
                with self.subTest(file=name, condition="tampered"):
                    (output / name).write_bytes(b"tampered content")
                    self.assertIsNone(find_existing(root, fingerprint, refresh))
                    (output / name).write_bytes(baseline[name])
                    self.assertIsNotNone(find_existing(root, fingerprint, refresh))
                with self.subTest(file=name, condition="missing"):
                    (output / name).unlink()
                    self.assertIsNone(find_existing(root, fingerprint, refresh))
                    (output / name).write_bytes(baseline[name])
                    self.assertIsNotNone(find_existing(root, fingerprint, refresh))
            self.assertEqual((output / "manifest.json").read_bytes(), original_manifest)
            self.assertEqual(
                {name: (output / name).read_bytes() for name in required},
                baseline,
            )

    def test_find_existing_ai_snapshot_requires_both_hashed_ai_artifacts(self) -> None:
        import hashlib

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "consolidated" / "CONS-AI-OFFLINE"
            folder.mkdir(parents=True)
            names = (
                "report.html", "decision-context.json", "longitudinal-evidence.json",
                "execution.json", "specialist-analysis.json", "ai-exchanges.json",
            )
            for name in names:
                (folder / name).write_text("{}", encoding="utf-8")
            fingerprint = request_fingerprint("source", ConsolidationFilter())
            payload = {
                "report_format_version": REPORT_FORMAT_VERSION,
                "request_fingerprint": fingerprint,
                "materialization_contract": MATERIALIZATION_CONTRACT,
                "temporal_apdex": {"contract": "TEMPORAL-APDEX-001"},
                "longitudinal_analysis": {
                    "contract": LONGITUDINAL_CONTRACT,
                    "catalog_contract": "CONSOLIDATED-CATALOG-LONGITUDINAL-006",
                    "ai_status": "COMPLETE",
                },
                "source_governance": {"contract": "CONSOLIDATED-SOURCE-GOVERNANCE-003"},
                "decision_context": {"contract": "CONSOLIDATED-DECISION-CONTEXT-002"},
                "specialist_ai": {"requested": True, "status": "COMPLETE"},
                "package_integrity": {
                    "files": {
                        name: {"sha256": hashlib.sha256((folder / name).read_bytes()).hexdigest()}
                        for name in names
                    }
                },
            }
            manifest = folder / "manifest.json"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            refresh = RefreshResult(1, 0, 1, 0, ())
            self.assertIsNotNone(find_existing(root, fingerprint, refresh))
            for name in ("specialist-analysis.json", "ai-exchanges.json"):
                artifact = folder / name
                with self.subTest(name=name, failure="tampered"):
                    artifact.write_text('{"modified":true}', encoding="utf-8")
                    self.assertIsNone(find_existing(root, fingerprint, refresh))
                    artifact.write_text("{}", encoding="utf-8")
                    self.assertIsNotNone(find_existing(root, fingerprint, refresh))
                with self.subTest(name=name, failure="missing"):
                    artifact.unlink()
                    self.assertIsNone(find_existing(root, fingerprint, refresh))
                    artifact.write_text("{}", encoding="utf-8")
                    self.assertIsNotNone(find_existing(root, fingerprint, refresh))
            payload["specialist_ai"]["status"] = "UNAVAILABLE"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(find_existing(root, fingerprint, refresh))

    def test_request_fingerprint_is_stable_and_filter_sensitive(self) -> None:
        base = request_fingerprint("source", ConsolidationFilter())
        self.assertEqual(base, request_fingerprint("source", ConsolidationFilter()))
        self.assertNotEqual(base, request_fingerprint("other", ConsolidationFilter()))
        self.assertNotEqual(
            base,
            request_fingerprint("source", ConsolidationFilter(devices=("MOBILE",))),
        )


    def test_request_fingerprint_rejects_pre_materialization_contract_snapshot(self) -> None:
        filters = ConsolidationFilter()
        legacy_payload = {
            "report_format_version": REPORT_FORMAT_VERSION,
            "temporal_contract": "TEMPORAL-APDEX-001",
            "longitudinal_contract": LONGITUDINAL_CONTRACT,
            "filters": filters.canonical(),
            "source_fingerprint": "source",
        }
        import hashlib
        legacy_material = json.dumps(
            legacy_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        legacy_fingerprint = hashlib.sha256(legacy_material.encode("utf-8")).hexdigest()
        self.assertNotEqual(
            legacy_fingerprint,
            request_fingerprint("source", filters),
        )



if __name__ == "__main__":
    unittest.main()
