"""Bounded daily MaxMind maintenance entry point; never imported by AUD processing."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from rasai.network_geoip_install import install_official_updater
from rasai.network_geoip_operations import operational_home, run_authorized_update

INTERVAL_SECONDS = 24 * 60 * 60


def run_daily(config: Path, *, licensed: bool, allow_install: bool = False,
              now: datetime | None = None) -> dict:
    """Daily check only when operator has already accepted MaxMind terms.

    This is intended for an external scheduler, not an audit or report.
    """
    if not licensed:
        return {"state": "NOT_CONFIGURED", "error": "LICENSE_NOT_CONFIRMED"}
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Data sem fuso")
    root = operational_home()
    state = root / "data" / "geoip" / "last-check.json"
    if state.is_file() and not state.is_symlink():
        try:
            previous = json.loads(state.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(previous["checked_utc"])
            age = (current - stamp).total_seconds()
            if 0 <= age < INTERVAL_SECONDS:
                return {"state": "UP_TO_DATE", "error": None}
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            pass
    install = install_official_updater(acquisition_authorized=allow_install)
    if install.get("state") not in ("READY", "INSTALLED"):
        return {"state": "NOT_CONFIGURED", "error": install.get("error")}
    outcome = run_authorized_update(config, licensed=True)
    if outcome["state"] == "UPDATED":
        state.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=state.parent,
                                         prefix=".geoip-check-", suffix=".tmp",
                                         delete=False) as stream:
            temp = Path(stream.name)
            json.dump({"checked_utc": current.isoformat()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temp, state)
        finally:
            temp.unlink(missing_ok=True)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description="Manutenção GeoIP independente da auditoria")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--license-accepted", action="store_true")
    parser.add_argument("--allow-install", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_daily(args.config, licensed=args.license_accepted,
                               allow_install=args.allow_install)))


if __name__ == "__main__":
    main()
