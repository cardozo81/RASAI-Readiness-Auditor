"""Common HTTP-reason classification never depends on Docker or live URLs."""
from types import SimpleNamespace
import pytest

from rasai.architecture_public_html import public_html_failure
from rasai.search_intelligence.content import ContentFetchStatus


@pytest.mark.parametrize("status,http_status,error,mime,final,reason", [
    (ContentFetchStatus.OBSERVED, 200, None, "text/html", "https://example.org/", None),
    (ContentFetchStatus.ERROR, 301, "TOO_MANY_REDIRECTS", "", None, "PUBLIC_REDIRECT_NOT_FOLLOWED"),
    (ContentFetchStatus.ERROR, 200, "CONTENT_BODY_LIMIT", "", None, "PUBLIC_HTML_SIZE_LIMIT"),
    (ContentFetchStatus.BLOCKED, None, None, "", None, "PUBLIC_DESTINATION_REJECTED"),
    (ContentFetchStatus.UNAVAILABLE, None, "CONTENT_TIMEOUT", "", None, "PUBLIC_TRANSPORT_UNAVAILABLE"),
    (ContentFetchStatus.OBSERVED, 301, None, "text/html", None, "PUBLIC_REDIRECT_NOT_FOLLOWED"),
    (ContentFetchStatus.OBSERVED, 403, None, "text/html", None, "PUBLIC_HTTP_NOT_SUCCESS"),
    (ContentFetchStatus.OBSERVED, 200, None, "text/html", "https://other.example.org/", "PUBLIC_FINAL_URL_MISMATCH"),
    (ContentFetchStatus.OBSERVED, 200, None, "application/json", "https://example.org/", "PUBLIC_RESPONSE_NOT_HTML"),
])
def test_both_acquisition_modes_share_identical_safe_diagnostic(
    status, http_status, error, mime, final, reason
):
    document = SimpleNamespace(
        status=status, http_status=http_status, error_code=error,
        headers={"content-type": mime}, final_url=final,
    )
    assert public_html_failure(document, "https://example.org/") == reason
