from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from rasai.consolidation.models import ConsolidationFilter
from rasai.consolidation.temporal_apdex import (
    TEMPORAL_APDEX_CONTRACT,
    augment_manifest,
    augment_report,
    build_temporal_apdex,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_temporal_audit(
    root: Path,
    audit_id: str,
    *,
    day: int,
    threshold: float = 2.0,
    nav_durations: tuple[float, ...] = (1000.0, 2000.0),
    nav_counts: tuple[int, int, int] = (2, 0, 0),
    include_experience: bool = False,
) -> dict[str, str]:
    workspace = root / audit_id
    workspace.mkdir(parents=True)
    db = workspace / "audit.db"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE synthetic_apdex_runs(
            audit_id TEXT, task_id TEXT, delay_seconds REAL, concurrency INTEGER
        );
        CREATE TABLE synthetic_apdex_summaries(
            audit_id TEXT,url TEXT,device TEXT,calculated_at TEXT,task_id TEXT,profile_id TEXT,
            threshold_seconds REAL,frustration_seconds REAL,valid_samples INTEGER,invalid_samples INTEGER,
            satisfied_count INTEGER,tolerating_count INTEGER,frustrated_count INTEGER,
            small_group INTEGER,final_group INTEGER
        );
        CREATE TABLE synthetic_apdex_samples(
            audit_id TEXT,url TEXT,device TEXT,run_index INTEGER,classification TEXT,
            duration_ms REAL,captured_at TEXT
        );
        CREATE TABLE synthetic_ux_apdex_runs(
            audit_id TEXT,task_id TEXT,device_mix TEXT,session_mode TEXT,kpm TEXT,
            satisfied_threshold_seconds REAL,frustrated_threshold_seconds REAL,
            errors_affect_apdex INTEGER,error_scope TEXT,settle_seconds REAL,
            calibration_source TEXT,configuration TEXT
        );
        CREATE TABLE synthetic_ux_apdex_summaries(
            audit_id TEXT,url TEXT,device TEXT,calculated_at TEXT,task_id TEXT,profile_id TEXT,
            valid_samples INTEGER,invalid_samples INTEGER,satisfied_count INTEGER,
            tolerating_count INTEGER,frustrated_count INTEGER,small_group INTEGER,final_group INTEGER
        );
        CREATE TABLE synthetic_ux_apdex_samples(
            audit_id TEXT,url TEXT,device TEXT,run_index INTEGER,classification TEXT,
            kpm_value_ms REAL,captured_at TEXT
        );
        """
    )
    url = "https://example.com/a"
    when = f"2026-09-{day:02d}T10:00:00-03:00"
    connection.execute(
        "INSERT INTO synthetic_apdex_runs VALUES (?,?,?,?)",
        (audit_id, "NAVIGATION_LOAD", 1.0, 1),
    )
    satisfied, tolerating, frustrated = nav_counts
    valid = satisfied + tolerating + frustrated
    connection.execute(
        "INSERT INTO synthetic_apdex_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            audit_id, url, "MOBILE", when, "NAVIGATION_LOAD", "RASAI_MOBILE_TEST",
            threshold, threshold * 4.0, valid, 0, satisfied, tolerating, frustrated, 1, 0,
        ),
    )
    classes = (
        ["SATISFIED"] * satisfied
        + ["TOLERATING"] * tolerating
        + ["FRUSTRATED"] * frustrated
    )
    for run_index, (duration, classification) in enumerate(zip(nav_durations, classes), 1):
        connection.execute(
            "INSERT INTO synthetic_apdex_samples VALUES (?,?,?,?,?,?,?)",
            (
                audit_id, url, "MOBILE", run_index, classification, duration,
                when.replace("10:00:00", f"10:00:{run_index:02d}"),
            ),
        )

    if include_experience:
        configuration = json.dumps({"delay_seconds": 1.0, "concurrency": 1})
        connection.execute(
            "INSERT INTO synthetic_ux_apdex_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                audit_id, "SYNTHETIC_LOAD_ACTION",
                json.dumps({"mobile": 60, "desktop": 35, "tablet": 5}),
                "cold", "USER_ACTION_DURATION", 3.0, 12.0, 1, "first-party", 5.0,
                "RASAI", configuration,
            ),
        )
        for device, profile in (("MOBILE", "UX-MOBILE"), ("POPULATION", "UX-POPULATION")):
            connection.execute(
                "INSERT INTO synthetic_ux_apdex_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    audit_id, url, device, when, "SYNTHETIC_LOAD_ACTION", profile,
                    2, 0, 1, 1, 0, 1, 0,
                ),
            )
        for run_index, duration in enumerate((2500.0, 5000.0), 1):
            connection.execute(
                "INSERT INTO synthetic_ux_apdex_samples VALUES (?,?,?,?,?,?,?)",
                (
                    audit_id, url, "MOBILE", run_index,
                    "SATISFIED" if run_index == 1 else "TOLERATING",
                    duration, when.replace("10:00:00", f"10:01:{run_index:02d}"),
                ),
            )

    connection.commit()
    connection.close()
    return {"audit_id": audit_id, "db_path": f"{audit_id}/audit.db"}


class TemporalApdexConsolidationTests(unittest.TestCase):
    def test_navigation_recalculates_period_score_and_percentiles_from_raw_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _make_temporal_audit(
                root, "AUD-1", day=1, nav_durations=(1000.0, 2000.0), nav_counts=(2, 0, 0)
            )
            second = _make_temporal_audit(
                root, "AUD-2", day=2, nav_durations=(3000.0, 4000.0), nav_counts=(0, 2, 0)
            )
            before = {
                root / first["db_path"]: _digest(root / first["db_path"]),
                root / second["db_path"]: _digest(root / second["db_path"]),
            }
            result = build_temporal_apdex(
                audits_root=root,
                audits=(first, second),
                filters=ConsolidationFilter(),
            )
            navigation = next(item for item in result if item.kind == "NAVIGATION")
            self.assertEqual(navigation.audits, 2)
            self.assertEqual(navigation.valid_samples, 4)
            self.assertAlmostEqual(navigation.apdex_score or 0.0, 0.75)
            self.assertAlmostEqual(navigation.duration_median_ms or 0.0, 2500.0)
            self.assertAlmostEqual(navigation.duration_p95_ms or 0.0, 3850.0)
            self.assertEqual(navigation.samples_with_duration, 4)
            self.assertEqual(before, {path: _digest(path) for path in before})

    def test_methodologically_incompatible_thresholds_are_never_merged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _make_temporal_audit(root, "AUD-1", day=1, threshold=2.0)
            second = _make_temporal_audit(root, "AUD-2", day=2, threshold=3.0)
            result = [
                item for item in build_temporal_apdex(
                    audits_root=root,
                    audits=(first, second),
                    filters=ConsolidationFilter(),
                )
                if item.kind == "NAVIGATION"
            ]
            self.assertEqual(len(result), 2)
            self.assertEqual({item.threshold_seconds for item in result}, {2.0, 3.0})

    def test_experience_population_uses_the_raw_device_sample_union(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = _make_temporal_audit(root, "AUD-1", day=1, include_experience=True)
            second = _make_temporal_audit(root, "AUD-2", day=2, include_experience=True)
            result = build_temporal_apdex(
                audits_root=root,
                audits=(first, second),
                filters=ConsolidationFilter(),
            )
            population = next(
                item for item in result
                if item.kind == "EXPERIENCE" and item.device == "POPULATION"
            )
            self.assertEqual(population.valid_samples, 4)
            self.assertEqual(population.samples_with_duration, 4)
            self.assertAlmostEqual(population.apdex_score or 0.0, 0.75)
            self.assertAlmostEqual(population.duration_median_ms or 0.0, 3750.0)

    def test_report_and_manifest_augmentation_preserve_unrelated_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = _make_temporal_audit(root, "AUD-1", day=1, include_experience=True)
            result = build_temporal_apdex(
                audits_root=root,
                audits=(audit,),
                filters=ConsolidationFilter(),
            )
            report = root / "report.html"
            report.write_text(
                "<html><section id='scores'>keep</section>"
                "<section id='apdex'><p>legacy</p></section>"
                "<section id='findings'>keep2</section></html>",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"aggregation_policy": {"missing_data": "never_zero"}}),
                encoding="utf-8",
            )
            self.assertTrue(augment_report(report, result))
            self.assertTrue(augment_manifest(manifest, result))
            html = report.read_text(encoding="utf-8")
            self.assertIn("<section id='scores'>keep</section>", html)
            self.assertIn("<section id='findings'>keep2</section>", html)
            self.assertIn("Apdex sintético no período", html)
            self.assertIn("conjunto bruto de amostras", html)
            self.assertIn("p95", html)
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["temporal_apdex"]["contract"], TEMPORAL_APDEX_CONTRACT)
            self.assertFalse(payload["temporal_apdex"]["raw_samples_persisted_in_manifest"])
            self.assertEqual(payload["aggregation_policy"]["missing_data"], "never_zero")


if __name__ == "__main__":
    unittest.main()
