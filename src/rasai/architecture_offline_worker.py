"""Networkless renderer used only inside the OCI architecture probe sandbox.

Input: bounded JSON through stdin. Output: bounded JSON on stdout.
The worker never resolves DNS, opens HTTP sockets or reads an AUD workspace.
Network egress is denied by the *container runtime* (--network none).
"""
from __future__ import annotations

import base64
import json
import sys
from typing import Any

from rasai.url_utils import normalize_url, normalized_origin

MAX_MANIFEST_BYTES = 5_000_000
MAX_RENDER_BYTES = 1_000_000
MAX_ENTRIES = 31


def validate_bundle(payload: object) -> tuple[str, str, dict[str, tuple[bytes, str, int]]]:
    if not isinstance(payload, dict) or set(payload) != {"url", "device", "resources"}:
        raise ValueError("Invalid offline browser manifest")
    target = payload["url"]
    device = payload["device"]
    resources = payload["resources"]
    if (not isinstance(target, str) or len(target) > 2048
            or normalize_url(target) != target
            or device not in {"mobile", "desktop"}
            or not isinstance(resources, list)
            or not 1 <= len(resources) <= MAX_ENTRIES):
        raise ValueError("Invalid offline capture target or resource count")
    table: dict[str, tuple[bytes, str, int]] = {}
    total_bytes = 0
    for record in resources:
        if not isinstance(record, dict) or set(record) != {"url", "body_b64", "content_type", "status"}:
            raise ValueError("Invalid offline resource")
        url, body_text, mime, status = (record[k] for k in ("url", "body_b64", "content_type", "status"))
        if (not isinstance(url, str) or len(url) > 2048
                or normalize_url(url) != url
                or normalized_origin(url) != normalized_origin(target)
                or url in table or not isinstance(body_text, str)
                or not isinstance(mime, str) or not 0 < len(mime) < 256
                or "\r" in mime or "\n" in mime
                or type(status) is not int or not 200 <= status < 300):
            raise ValueError("Offline resource identity/status invalid")
        try:
            body = base64.b64decode(body_text, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ValueError("Malformed offline resource") from exc
        total_bytes += len(body)
        if total_bytes > 3_000_000:
            raise ValueError("Offline resource budget exceeded")
        table[url] = (body, mime, status)
    if target not in table or "text/html" not in table[target][1].lower():
        raise ValueError("Missing HTML entry document")
    return target, device, table


def render_bundle(target: str, device: str, table: dict[str, tuple[bytes, str, int]]) -> dict[str, Any]:
    from playwright.sync_api import Error as BrowserError, TimeoutError as BrowserTimeout, sync_playwright
    from rasai.rendering import DESKTOP_PROFILE, MOBILE_PROFILE

    requested = [0]
    blocked = [0]
    served = set()
    profile = DESKTOP_PROFILE if device == "desktop" else MOBILE_PROFILE
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            try:
                context = browser.new_context(**profile.context_options, service_workers="block")
                try:
                    def offline_route(route):
                        requested[0] += 1
                        resource = table.get(route.request.url)
                        if (requested[0] > 30 or route.request.method != "GET"
                                or resource is None):
                            blocked[0] += 1
                            route.abort()
                            return
                        data, mime, status = resource
                        served.add(route.request.url)
                        route.fulfill(status=status, body=data, content_type=mime)

                    def offline_websocket(route):
                        blocked[0] += 1
                        route.close()

                    context.route("**/*", offline_route)
                    context.route_web_socket("**/*", offline_websocket)
                    page = context.new_page()
                    response = page.goto(target, wait_until="domcontentloaded", timeout=12_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=2_000)
                    except BrowserTimeout:
                        pass
                    if (response is None or not 200 <= response.status < 300
                            or normalize_url(page.url) != target):
                        return {"rendered_html": None, "reason": "ISOLATED_NAVIGATION_NOT_ATTESTED"}
                    rendered = page.content()
                    if len(rendered.encode("utf-8")) > MAX_RENDER_BYTES:
                        return {"rendered_html": None, "reason": "ISOLATED_RENDER_LIMIT"}
                    if blocked[0]:
                        return {"rendered_html": None, "reason": "ISOLATED_RESOURCES_BLOCKED"}
                    return {"rendered_html": rendered, "reason": None}
                finally:
                    context.close()
            finally:
                browser.close()
    except (BrowserError, BrowserTimeout, OSError, ValueError):
        return {"rendered_html": None, "reason": "ISOLATED_BROWSER_UNAVAILABLE"}


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ValueError("Offline manifest is too large")
        target, device, resources = validate_bundle(json.loads(raw))
        result = render_bundle(target, device, resources)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        result = {"rendered_html": None, "reason": "ISOLATED_MANIFEST_INVALID"}
    output = json.dumps(result, separators=(",", ":"), ensure_ascii=False)
    sys.stdout.write(output + "\n")
    return 0 if result["reason"] is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
