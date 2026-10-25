"""Bounded resource capture contract without HTTP requests or a browser."""
from rasai.device_context_capture import _observed_resource_metadata


def test_response_metadata_is_limited_without_new_egress():
    rows = {
        str(i): {"resource_type": "Stylesheet", "host": "cdn.example.org",
                 "status": 200} for i in range(180)
    }
    got = _observed_resource_metadata({
        "available": True, "resource_responses": rows,
        "resource_response_truncated": True,
    })
    assert got["count"] == 160
    assert len(got["items"]) == 160
    assert got["truncated"] is True
    assert got["additional_network_requests"] == 0


def test_network_unavailable_is_not_claimed_as_zero_capture():
    result = _observed_resource_metadata({})
    assert result["state"] == "UNAVAILABLE"
    assert result["count"] == 0
    assert result["additional_network_requests"] == 0
