"""#652: one-shot local Windows physical FAQ acceptance; never a general crawler mode.

Requires an elevated Windows terminal, Python/Playwright already installed, and
the operator's explicitly approved local-fixture scope. The temporary firewall
rule blocks Chromium outbound at OS level and is always removed. No secrets in
AUD/Git/log output. Result is intentionally conservative about independent
session attestation: existing receipt verifier does not claim that proof.
"""
from __future__ import annotations

import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Thread
from uuid import uuid4

PAGE = b"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>FAQ 652 - teste local controlado</title></head><body>
<main><h1>FAQ de homologacao RASAi</h1>
<button type="button" aria-controls="faq-answer-controlled" aria-expanded="false">
FAQ: como funciona esta demonstracao?</button>
<section id="faq-answer-controlled" hidden></section></main>
<script>
document.querySelector('button[aria-controls="faq-answer-controlled"]')
.addEventListener('click', () => {
  setTimeout(() => {
    document.getElementById('faq-answer-controlled').textContent =
      'Resposta inserida apos o clique autorizado, sem rede.';
    document.getElementById('faq-answer-controlled').hidden = false;
    document.querySelector('button[aria-controls="faq-answer-controlled"]')
      .setAttribute('aria-expanded', 'true');
  }, 90);
});
</script></body></html>"""


class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


def firewall(*args: str) -> None:
    result = subprocess.run(["netsh", "advfirewall", "firewall", *args],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError("Windows Firewall rejected or failed the scoped rule")


def run() -> int:
    if sys.platform != "win32":
        raise RuntimeError("this local physical acceptance requires Windows")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("execute in an elevated Windows PowerShell; do not disable Firewall")
    root = Path(__file__).resolve().parents[1]
    if not (root / "src" / "rasai" / "entrypoint.py").is_file():
        raise RuntimeError("run from the checked-out RASAi repository")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser_path = Path(playwright.chromium.executable_path).resolve()
    if not browser_path.is_file():
        raise RuntimeError("Playwright Chromium executable not installed")
    unique = uuid4().hex[:12]
    name = "RASAI-FAQ-652-" + unique
    workspace = Path(tempfile.mkdtemp(prefix="rasai-652-"))
    audit_root = workspace / "audits"
    secret_path = workspace / "collector.key"
    secret_path.write_bytes(os.urandom(32))
    # No other process should read the key; in particular, never put it in Git.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    target = "http://127.0.0.1:%d/" % server.server_port
    installed = False
    report: dict[str, object] = {
        "contract": "RASAI-652-WINDOWS-LOCAL-ACCEPTANCE-001",
        "target": target,
        "firewall_rule": name,
        "firewall_rule_installed": False,
        "audit_command_exit": None,
        "aud_id": None,
        "receipt_verified": False,
        "persistent_aud_dom_bound": False,
        "independent_same_session_attestation": False,
        "status": "NOT_EXECUTED",
        "log_path": str(workspace / "audit.log"),
    }
    try:
        # A recorded firewall rule alone is insufficient when Windows
        # Defender Firewall is disabled on any profile. Fail closed.
        profile_check = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "@(Get-NetFirewallProfile | Where-Object { -not $_.Enabled }).Count"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        if profile_check.returncode or profile_check.stdout.strip() != "0":
            raise RuntimeError("Windows Defender Firewall profiles are not all enabled")
        firewall("add", "rule", "name=" + name, "dir=out",
                 "action=block", "program=" + str(browser_path),
                 "enable=yes", "profile=any")
        installed = True
        firewall("show", "rule", "name=" + name)
        report["firewall_rule_installed"] = True
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root / "src")
        env["RASAI_PLAYWRIGHT_CHROMIUM_EXECUTABLE"] = str(browser_path)
        # Never activate or request provider calls / remote PageSpeed.
        args = [
            sys.executable, "-m", "rasai", "audit", target,
            "--project", "RASAI-652-CONTROLLED-DISPOSABLE",
            "--max-pages", "1", "--device-context", "mobile",
            "--ai-provider", "none", "--no-web-performance",
            "--no-ai-content-remediation", "--audits-root", str(audit_root),
            "--experimental-faq-explicit-consent",
            "--experimental-faq-network-boundary-ack",
            "--experimental-faq-requested-url", target,
            "--experimental-faq-allowed-final-url", target,
            "--experimental-faq-device", "MOBILE",
            "--experimental-faq-target-id", "faq-answer-controlled",
            "--experimental-faq-collector-id", "local-fixture-652",
            "--experimental-faq-trusted-key-file", str(secret_path),
        ]
        try:
            with (workspace / "audit.log").open("w", encoding="utf-8") as log:
                proc = subprocess.run(args, cwd=root, env=env,
                                      stdout=log, stderr=subprocess.STDOUT,
                                      timeout=360, check=False)
            report["audit_command_exit"] = proc.returncode
        except subprocess.TimeoutExpired:
            report["status"] = "AUDIT_TIMEOUT"
            return 3
        candidates = sorted(audit_root.glob("AUD-*"))
        if len(candidates) != 1:
            report["status"] = "NO_UNIQUE_AUD"
            return 3
        aud = candidates[0]
        report["aud_id"] = aud.name
        sidecars = audit_root / ".rasai-faq-sidecars" / aud.name
        receipts = list(sidecars.glob("*.json")) if sidecars.is_dir() else []
        if proc.returncode or len(receipts) != 1:
            report["status"] = "AUD_OR_RECEIPT_INCOMPLETE"
            return 3
        evidence = json.loads(receipts[0].read_text(encoding="utf-8"))
        verification = evidence.get("verification") or {}
        report["receipt_verified"] = verification.get(
            "signed_live_page_witness_valid") is True
        report["persistent_aud_dom_bound"] = verification.get(
            "persisted_dom_bytes_match_signed_receipt") is True
        report["independent_same_session_attestation"] = evidence.get(
            "same_persisted_browser_session_independently_attested") is True
        report["status"] = (
            "AUD_DOM_LINKED_NOT_INDEPENDENTLY_ATTESTED"
            if report["receipt_verified"] and report["persistent_aud_dom_bound"]
            else "RECEIPT_BINDING_FAILED"
        )
        # Do not claim full #652 acceptance while the verifier explicitly
        # declines an independent same-session attestation.
        return 0 if report["receipt_verified"] and report["persistent_aud_dom_bound"] else 3
    finally:
        server.shutdown()
        server.server_close()
        if installed:
            try:
                firewall("delete", "rule", "name=" + name)
            except Exception:
                report["firewall_cleanup_failed"] = True
        try:
            secret_path.unlink(missing_ok=True)
        finally:
            # Never expose key bytes, key hash, HTML snapshots or provider data.
            report["signing_key_removed"] = not secret_path.exists()
            report["evidence_root"] = str(audit_root)
            report_path = workspace / "result.json"
            report_path.write_text(json.dumps(report, indent=2, sort_keys=True),
                                   encoding="utf-8")
            print("RASAI_652_ACCEPTANCE_RESULT=" + str(report_path))
            print("RASAI_652_STATUS=" + str(report["status"]))
            if report.get("firewall_cleanup_failed"):
                print("ALERT: firewall cleanup failed; remove named rule as administrator.")


if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except Exception as error:
        print("RASAI_652_FAIL_CLOSED=" + type(error).__name__ + ": " + str(error))
        raise SystemExit(3)
