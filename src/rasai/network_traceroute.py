"""#659 G2: optional strictly bounded traceroute to a pinned vetted public IP."""
from __future__ import annotations

import ipaddress
import os
import re
import subprocess

MAX_HOPS = 8


def parse_trace(text: str, destination: str) -> dict:
    """Partial logical hop sequence; no private hop address or inferred link RTT."""
    hops = []
    dest = ipaddress.ip_address(destination)
    for line in text.splitlines()[:40]:
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
    return {"hops": hops, "target_reached": any(
        row["public_ip"] == str(dest) for row in hops
    ), "max_hops": MAX_HOPS, "trace_kind": "LOGICAL_HOPS_ONLY",
        "limitations": ["Saltos não descrevem coordenadas físicas.",
                        "RTT de um salto não equivale à latência de um enlace."]}


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
                                   timeout=8, check=False)
        if len(completed.stdout) > 65_536:
            raise ValueError("Resposta de caminho fora do limite")
        parsed = parse_trace(completed.stdout, str(address))
        return {"state": "OBSERVED" if parsed["hops"] else "INCONCLUSIVE",
                "value": parsed if parsed["hops"] else None,
                "error": (None if parsed["target_reached"] else "ROUTE_NOT_CONFIRMED")}
    except FileNotFoundError:
        return {"state": "NOT_APPLICABLE", "value": None,
                "error": "TRACE_COMMAND_NOT_AVAILABLE"}
    except subprocess.TimeoutExpired:
        return {"state": "INCONCLUSIVE", "value": None, "error": "TRACE_TIME_BUDGET_EXCEEDED"}
    except (OSError, ValueError, UnicodeError):
        return {"state": "COLLECTION_FAILED", "value": None,
                "error": "TRACE_COLLECTION_FAILED"}
