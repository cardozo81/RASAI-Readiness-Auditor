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
    (ContentFetchStatus.UNAVAILABLE, None, "CONTENT_TIMEOUT", "", None, "PUBLIC_TIMEOUT"),
    (ContentFetchStatus.UNAVAILABLE, None, "CONTENT_TLS_ERROR", "", None, "PUBLIC_TLS_FAILURE"),
    (ContentFetchStatus.UNAVAILABLE, None, "CONTENT_NETWORK_ERROR", "", None, "PUBLIC_NETWORK_FAILURE"),
    (ContentFetchStatus.UNAVAILABLE, None, "UNRECOGNIZED_ERROR", "", None, "PUBLIC_TRANSPORT_UNAVAILABLE"),
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



def test_646_follow_at_most_two_host_related_https_safe_redirects_without_false_spa():
    from rasai.architecture_public_html import verified_public_redirect_chain
    assert verified_public_redirect_chain(
        "http://example.org/", "https://www.example.org/home",
        ("https://example.org/", "https://www.example.org/home"),
    )
    assert verified_public_redirect_chain(
        "https://example.org/", "https://www.example.org/", ("https://www.example.org/",),
    )
    assert not verified_public_redirect_chain(
        "https://example.org/", "http://example.org/", ("http://example.org/",),
    )
    assert not verified_public_redirect_chain(
        "https://example.org/", "https://other.org/", ("https://other.org/",),
    )
    assert not verified_public_redirect_chain(
        "https://example.org/", "https://example.org/other", (),
    )
    assert not verified_public_redirect_chain(
        "https://example.org/", "https://example.org/three",
        ("https://example.org/one", "https://example.org/two", "https://example.org/three"),
    )
    assert not verified_public_redirect_chain(
        "https://example.org/", "https://example.org/",
        ("https://example.org/one", "https://example.org/"),
    )


def test_646_final_tls_authenticated_redirect_requires_matching_chain():
    from rasai.architecture_public_html import public_html_failure
    from types import SimpleNamespace
    from rasai.search_intelligence.content import ContentFetchStatus
    target = "http://example.org/"
    accepted = SimpleNamespace(
        status=ContentFetchStatus.OBSERVED, http_status=200, error_code=None,
        headers={"content-type": "text/html"}, final_url="https://example.org/",
        redirects=("https://example.org/",),
    )
    assert public_html_failure(accepted, target) is None
    assert public_html_failure(
        SimpleNamespace(**{**vars(accepted), "redirects": ()}), target,
    ) == "PUBLIC_FINAL_URL_MISMATCH"
    assert public_html_failure(
        SimpleNamespace(**{**vars(accepted),
                          "status": ContentFetchStatus.UNAVAILABLE,
                          "error_code": "CONTENT_TLS_ERROR"}),
        target,
    ) == "PUBLIC_TLS_FAILURE"
    assert public_html_failure(
        SimpleNamespace(**{**vars(accepted), "status": ContentFetchStatus.ERROR,
                          "error_code": "REDIRECT_LOOP"}),
        target,
    ) == "PUBLIC_REDIRECT_UNVERIFIABLE"
