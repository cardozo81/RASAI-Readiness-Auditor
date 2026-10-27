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
MAX_HOPS_HARD_LIMIT = 16
MAX_TRACE_SECONDS = 40


def parse_trace(text: str, destination: str, *, max_hops: int = MAX_HOPS) -> dict:
    """Partial logical hop sequence; no private hop address or inferred link RTT."""
    if type(max_hops) is not int or not 1 <= max_hops <= MAX_HOPS_HARD_LIMIT:
        raise ValueError("Limite de hops inválido")
    hops = []
    dest = ipaddress.ip_address(destination)
    for line in text.splitlines()[:64]:
        match = re.match(r"\s*(\d{1,2})\s+", line)
        if not match:
            continue
        number = int(match.group(1))
        if not (1 <= number <= max_hops) or any(row["hop"] == number for row in hops):
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
        # Retain the individual probe samples; no link RTT is inferred.
        samples = []
        for sample in re.finditer(r"(?<![<\d])([0-9]+(?:\.[0-9]+)?)\s*ms\b", line, re.I):
            elapsed_sample = float(sample.group(1))
            if 0 <= elapsed_sample <= 60000:
                samples.append(elapsed_sample)
        samples = samples[:3]
        elapsed = samples[0] if samples else None
        hops.append({
            "hop": number, "state": (
                "NO_REPLY" if found is None else
                ("PUBLIC_HOP" if found.is_global else "PRIVATE_HOP_REDACTED")),
            "public_ip": str(found) if found is not None and found.is_global else None,
            "rtt_ms": elapsed,
            "rtt_samples_ms": samples,
        })
    return {"schema": "rasai-network-logical-trace-v2", "hops": hops, "last_responding_hop": max(
        (row["hop"] for row in hops if row["state"] != "NO_REPLY"), default=None),
        "target_reached": any(
        row["public_ip"] == str(dest) for row in hops
    ), "max_hops": max_hops, "trace_kind": "LOGICAL_HOPS_ONLY",
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


def _result(raw: str, destination: str, *, timed_out: bool = False,
            returncode: int = 0, max_hops: int = MAX_HOPS) -> dict:
    parsed = parse_trace(raw, destination, max_hops=max_hops)
    has_hops = bool(parsed["hops"])
    parsed["partial"] = timed_out or not parsed["target_reached"]
    parsed["probe_protocol"] = "ICMP" if os.name == "nt" else "TCP"
    parsed["method"] = "WINDOWS_TRACERT" if os.name == "nt" else "LINUX_TRACEROUTE_TCP"
    parsed["measurement_origin"] = "LOCAL_OPERATOR_PROCESS"
    parsed["collection_status"] = ("TIME_BUDGET_EXCEEDED" if timed_out else
                                   "NONZERO_EXIT" if returncode != 0 else "COMPLETED_PROCESS")
    return {
        "state": "OBSERVED" if has_hops else "INCONCLUSIVE",
        "value": parsed if has_hops else None,
        "error": ("TRACE_TIME_BUDGET_EXCEEDED" if timed_out else
                  "TRACE_COMMAND_FAILED" if returncode != 0 else
                  None if parsed["target_reached"] else "ROUTE_NOT_CONFIRMED"),
    }


def bounded_trace(ip: str, port: int, *, max_hops: int = MAX_HOPS) -> dict:
    if type(max_hops) is not int or not 1 <= max_hops <= MAX_HOPS_HARD_LIMIT:
        raise ValueError("Limite de hops inválido")
    address = ipaddress.ip_address(ip)
    if not address.is_global or port not in (80, 443):
        raise ValueError("Sondagem de caminho não autorizada")
    if os.name == "nt":
        cmd = ["tracert", "-d", "-h", str(max_hops), "-w", "500", str(address)]
    else:
        cmd = ["traceroute", "-n", "-T", "-m", str(max_hops),
               "-q", "1", "-w", "1", "-p", str(port), str(address)]
    deadline = min(MAX_TRACE_SECONDS, max(6, max_hops * (1.5 if os.name == 'nt' else 1.0) + 4))
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=deadline, check=False)
        if len(completed.stdout) > 65_536:
            raise ValueError("Resposta de caminho fora do limite")
        return _result(completed.stdout, str(address),
                       returncode=completed.returncode, max_hops=max_hops)
    except FileNotFoundError:
        return {"state": "NOT_APPLICABLE", "value": None,
                "error": "TRACE_COMMAND_NOT_AVAILABLE"}
    except subprocess.TimeoutExpired as exc:
        return _result(_partial_text(exc.stdout), str(address), timed_out=True,
                       max_hops=max_hops)
    except (OSError, ValueError, UnicodeError):
        return {"state": "COLLECTION_FAILED", "value": None,
                "error": "TRACE_COLLECTION_FAILED"}
