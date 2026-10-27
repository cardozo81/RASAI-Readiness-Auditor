"""#659 G2: optional strictly bounded traceroute to a pinned vetted public IP."""
from __future__ import annotations

import ipaddress
import os
import re
import subprocess

# Windows tracert can wait 3 × 500 ms per hop, plus process overhead.
# Keep the subprocess deadline below the parent worker's allotted budget.
TRACE_TIMEOUT_SECONDS = 16

MAX_HOPS = 8


def parse_trace(text: str, destination: str) -> dict:
    """Partial logical hop sequence; no private hop address or inferred link RTT."""
    hops = []
    dest = ipaddress.ip_address(destination)
    for line in text.splitlines()[:64]:
        match = re.match(r"\s*(\d{1,2})\s+", line)
        if not match:
            continue
        number = int(match.group(1))
        if not (1 <= number <= MAX_HOPS) or any(row["hop"] == number for row in hops):
            continue
        found = None
        for token in re.split(r"\s+", line):
            raw = token.strip("[]()")
            try:
                maybe = ipaddress.ip_address(raw)
            except ValueError:
                continue
            found = maybe
            break
        rtt = re.search(r"(?<![<\d])([0-9]+(?:\.[0-9]+)?)\s*ms\b", line, re.I)
        elapsed = float(rtt.group(1)) if rtt else None
        if elapsed is not None and elapsed > 60000:
            elapsed = None
        hops.append({
            "hop": number, "state": (
                "NO_REPLY" if found is None else
                ("PUBLIC_HOP" if found.is_global else "PRIVATE_HOP_REDACTED")),
            "public_ip": str(found) if found is not None and found.is_global else None,
            "rtt_ms": elapsed,
        })
    return {"hops": hops, "last_responding_hop": max(
        (row["hop"] for row in hops if row["state"] != "NO_REPLY"), default=None),
        "target_reached": any(
        row["public_ip"] == str(dest) for row in hops
    ), "max_hops": MAX_HOPS, "trace_kind": "LOGICAL_HOPS_ONLY",
        "limitations": ["Saltos não descrevem coordenadas físicas.",
                        "RTT de um salto não equivale à latência de um enlace."]}


def _partial_text(value: bytes | str | None) -> str:
    """Decode TimeoutExpired stdout without leaking binary data or unlimited output."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        # UTF-8 for modern environments; Windows console code pages as fallback.
        for encoding in ("utf-8", "cp850", "cp1252"):
            try:
                return value[:65_536].decode(encoding)
            except UnicodeDecodeError:
                continue
        return value[:65_536].decode("utf-8", errors="replace")
    return value[:65_536]


def _result(raw: str, destination: str, *, timed_out: bool = False) -> dict:
    parsed = parse_trace(raw, destination)
    has_hops = bool(parsed["hops"])
    parsed["partial"] = timed_out or not parsed["target_reached"]
    parsed["collection_status"] = "TIME_BUDGET_EXCEEDED" if timed_out else "COMPLETED_PROCESS"
    return {
        "state": "OBSERVED" if has_hops else "INCONCLUSIVE",
        "value": parsed if has_hops else None,
        "error": ("TRACE_TIME_BUDGET_EXCEEDED" if timed_out else
                  None if parsed["target_reached"] else "ROUTE_NOT_CONFIRMED"),
    }


def bounded_trace(ip: str, port: int) -> dict:
    address = ipaddress.ip_address(ip)
    if not address.is_global or port not in (80, 443):
        raise ValueError("Sondagem de caminho não autorizada")
    if os.name == "nt":
        cmd = ["tracert", "-d", "-h", str(MAX_HOPS), "-w", "500", str(address)]
    else:
        cmd = ["traceroute", "-n", "-T", "-m", str(MAX_HOPS),
               "-q", "1", "-w", "1", "-p", str(port), str(address)]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=TRACE_TIMEOUT_SECONDS, check=False)
        if len(completed.stdout) > 65_536:
            raise ValueError("Resposta de caminho fora do limite")
        return _result(completed.stdout, str(address))
    except FileNotFoundError:
        return {"state": "NOT_APPLICABLE", "value": None,
                "error": "TRACE_COMMAND_NOT_AVAILABLE"}
    except subprocess.TimeoutExpired as exc:
        return _result(_partial_text(exc.stdout), str(address), timed_out=True)
    except (OSError, ValueError, UnicodeError):
        return {"state": "COLLECTION_FAILED", "value": None,
                "error": "TRACE_COLLECTION_FAILED"}
