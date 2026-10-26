"""Issue #665: shared parsing, secret assurance and public label regressions."""
from __future__ import annotations

from rasai.extraction import ContentExtractor
from rasai.secret_safety import detect_secret_exposures, redact_text
from rasai.catalog_report_public_labels import public_label


def test_r01_only_head_title_enters_document_title():
    html = """<html><head><title>Wikipedia</title></head><body>
    <svg><title>Wikimedia Foundation</title></svg>
    <main><h1>Enciclopédia</h1></main></body></html>"""
    page = ContentExtractor().extract(html)
    assert page.title == "Wikipedia"
    assert "Wikimedia Foundation" not in page.main_content


def test_r01_svg_titles_before_head_and_malformed_graphics_do_not_pollute_title():
    html = """<html><svg><title>Gráfico</title></svg>
    <head><title>Blog Tool, Publishing Platform, and CMS – WordPress.org</title></head>
    <body><svg><title>WordPress.org</title><title>Code is Poetry</title></svg></body></html>"""
    assert ContentExtractor().extract(html).title == "Blog Tool, Publishing Platform, and CMS – WordPress.org"
    malformed = "<html><head><title>Principal</title></head><body><svg><title>Outro"
    assert ContentExtractor().extract(malformed).title == "Principal"


def test_r05_invalid_serialized_json_url_not_credential():
    # The old regex crossed JSON backslashes and quotes into another field.
    serialized = r'{"content":"https://viewer.example\\",\\"another\\":\\"foo:bar@elsewhere.test"}'
    assert not any(f.kind == "CREDENTIAL_URL" for f in detect_secret_exposures(
        serialized, path="ai-integrations.html", strict=True, html_dom_context=True
    ))


def test_r05_real_uri_userinfo_remains_blocked_and_redacted():
    urls = (
        "postgresql://user:synthetic_password_93af@db.example.test:5432/database",
        "https://viewer:synthetic_password_93af@host.example.test/path",
        "https://user:synthetic_password_93af@[2001:db8::1]/path",
    )
    for url in urls:
        assert any(f.kind == "CREDENTIAL_URL" for f in detect_secret_exposures(url, strict=True))
        assert "synthetic_password_93af" not in redact_text(url)
    assert any(f.kind == "BEARER_TOKEN" for f in detect_secret_exposures("Bearer synthetic_token_93af"))
    assert any(f.kind == "KNOWN_SECRET_PATTERN" for f in detect_secret_exposures(
        "sk-proj-" + "A" * 28, strict=True, html_dom_context=True))


def test_r06_only_known_normative_labels_are_localized():
    assert public_label("Canonical declarations must be interpretable and non-conflicting") == (
        "As declarações canonical devem ser interpretáveis e não conflitantes")
    assert public_label("robots.txt must be interpretable when present") == (
        "O robots.txt deve ser interpretável quando estiver presente")
    assert public_label("Sitemap resources must be acquired and interpreted when available") == (
        "Os recursos de sitemap devem ser adquiridos e interpretados quando disponíveis")
