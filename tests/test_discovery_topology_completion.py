"""Regression tests for multi-file sitemap and llms.txt discovery topology."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from rasai.acquisition import HttpAcquisitionResult
from rasai.discovery import DiscoveryEngine, SitemapState
from rasai.m24_discovery_extensions import install_discovery_extensions
from rasai.m24_llms_discovery import analyze_llms_v2


def _response(url: str, status: int, body: bytes = b"", headers=()) -> HttpAcquisitionResult:
    return HttpAcquisitionResult(
        requested_url=url,
        final_url=url,
        status=status,
        headers=tuple(headers),
        body=body,
        redirects=(),
        network_error=None,
        elapsed_ms=1,
    )


class _MappingClient:
    def __init__(self, mapping: dict[str, HttpAcquisitionResult]) -> None:
        self.mapping = mapping
        self.seen: list[str] = []

    def acquire(self, url: str) -> HttpAcquisitionResult:
        self.seen.append(url)
        if url in self.mapping:
            return self.mapping[url]
        return _response(url, 404, b"missing", (("Content-Type", "text/plain"),))


class DiscoveryTopologyCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_discovery_extensions()

    def test_sitemap_can_live_below_root_and_expand_multiple_nested_files(self) -> None:
        origin = "https://example.test"
        robots_url = f"{origin}/robots.txt"
        index_url = f"{origin}/discovery/maps/index.xml"
        news_url = f"{origin}/discovery/maps/news.xml"
        blog_url = f"{origin}/blog/sitemap.xml"
        mapping = {
            robots_url: _response(
                robots_url,
                200,
                f"User-agent: *\nAllow: /\nSitemap: {index_url}\n".encode(),
                (("Content-Type", "text/plain"),),
            ),
            index_url: _response(
                index_url,
                200,
                (
                    "<sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                    f"<sitemap><loc>{news_url}</loc></sitemap>"
                    f"<sitemap><loc>{blog_url}</loc></sitemap>"
                    "</sitemapindex>"
                ).encode(),
                (("Content-Type", "application/xml"),),
            ),
            news_url: _response(
                news_url,
                200,
                (
                    "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                    f"<url><loc>{origin}/news/a</loc></url>"
                    "</urlset>"
                ).encode(),
                (("Content-Type", "application/xml"),),
            ),
            blog_url: _response(
                blog_url,
                200,
                (
                    "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
                    f"<url><loc>{origin}/blog/a</loc></url>"
                    "</urlset>"
                ).encode(),
                (("Content-Type", "application/xml"),),
            ),
            f"{origin}/": _response(
                f"{origin}/",
                200,
                b"<html><body><main>home</main></body></html>",
                (("Content-Type", "text/html"),),
            ),
            f"{origin}/news/a": _response(
                f"{origin}/news/a", 200, b"<html><body>news</body></html>", (("Content-Type", "text/html"),)
            ),
            f"{origin}/blog/a": _response(
                f"{origin}/blog/a", 200, b"<html><body>blog</body></html>", (("Content-Type", "text/html"),)
            ),
        }
        client = _MappingClient(mapping)
        result = DiscoveryEngine(client).discover(f"{origin}/", max_pages=3)
        acquired = {item.url: item for item in result.sitemaps}
        self.assertIn(index_url, acquired)
        self.assertIn(news_url, acquired)
        self.assertIn(blog_url, acquired)
        self.assertEqual(acquired[index_url].state, SitemapState.OBTAINED)
        self.assertEqual(set(acquired[index_url].child_sitemaps), {news_url, blog_url})
        self.assertNotEqual(index_url, f"{origin}/sitemap.xml")

    def test_llms_v2_uses_root_describedby_and_explicit_robots_hint_without_guessing(self) -> None:
        origin = "https://example.test"
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            database = root / "audit.db"
            html_ref = Path("artifacts/page.html")
            robots_ref = Path("artifacts/robots.response")
            (root / html_ref).write_text(
                "<html><head><link rel='describedby' href='/products/llms.txt'></head><body></body></html>",
                encoding="utf-8",
            )
            (root / robots_ref).write_text(
                "User-agent: *\nAllow: /\nLLMS: /docs/llms.txt\n",
                encoding="utf-8",
            )
            connection = sqlite3.connect(database)
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE pages(page_id TEXT PRIMARY KEY,normalized_url TEXT NOT NULL);
                    CREATE TABLE evidence(
                        evidence_id TEXT PRIMARY KEY,evidence_type TEXT,page_id TEXT,source TEXT,
                        observed_value TEXT,artifact_reference TEXT,captured_at TEXT
                    );
                    CREATE TABLE page_snapshots(
                        snapshot_id TEXT PRIMARY KEY,page_id TEXT,final_url TEXT,
                        rendered_artifact_ref TEXT,raw_artifact_ref TEXT
                    );
                    INSERT INTO pages VALUES ('P1','https://example.test/');
                    """
                )
                connection.execute(
                    "INSERT INTO evidence VALUES (?,?,?,?,?,?,?)",
                    (
                        "E-HTTP", "HTTP_RESPONSE", "P1", "http",
                        json.dumps({
                            "requested_url": f"{origin}/",
                            "final_url": f"{origin}/",
                            "headers": [["Link", "</support/llms.txt>; rel=\"describedby\""]],
                        }),
                        None, "2026-09-10T12:00:00Z",
                    ),
                )
                connection.execute(
                    "INSERT INTO evidence VALUES (?,?,?,?,?,?,?)",
                    (
                        "E-ROBOTS", "ROBOTS_RULE", None, f"{origin}/robots.txt",
                        json.dumps({"state": "OBTAINED"}), robots_ref.as_posix(),
                        "2026-09-10T12:00:01Z",
                    ),
                )
                connection.execute(
                    "INSERT INTO page_snapshots VALUES (?,?,?,?,?)",
                    ("S1", "P1", f"{origin}/", html_ref.as_posix(), None),
                )
            connection.close()

            urls = {
                f"{origin}/llms.txt": b"# Site\n\nRoot instructions.\n",
                f"{origin}/docs/llms.txt": b"# Docs\n\nScoped docs.\n",
                f"{origin}/support/llms.txt": b"# Support\n\nScoped support.\n",
                f"{origin}/products/llms.txt": b"# Products\n\nScoped products.\n",
            }
            client = _MappingClient({
                url: _response(url, 200, body, (("Content-Type", "text/plain"),))
                for url, body in urls.items()
            })
            workspace = SimpleNamespace(
                root=root,
                artifacts=artifacts,
                database=database,
            )
            state, diagnostics = analyze_llms_v2(
                origin=origin,
                workspace=workspace,
                client=client,
            )
            self.assertEqual(state, "PRESENT")
            present = [item for item in diagnostics if item.code == "M24-LLMS-PRESENT"]
            self.assertEqual({item.scope_url for item in present}, set(urls))
            self.assertEqual(set(client.seen), set(urls))
            self.assertEqual(len(client.seen), 4)
            self.assertIn("M24-LLMS-MULTIPLE-SCOPES", {item.code for item in diagnostics})
            self.assertIn("M24-LLMS-ROBOTS-NONSTANDARD-HINT", {item.code for item in diagnostics})
            artifact_refs = {
                item.observed["artifact_reference"]
                for item in present
            }
            self.assertEqual(len(artifact_refs), 4)
            self.assertTrue(all((root / ref).is_file() for ref in artifact_refs))
            self.assertNotIn(f"{origin}/blog/llms.txt", client.seen)


if __name__ == "__main__":
    unittest.main()
