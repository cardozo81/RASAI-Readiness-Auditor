"""One-shot explicit FAQ gesture policy and post-seal physical evidence (#652).

The isolated M3 browser worker holds the live page. Only an exact URL/device
scope may attach the opt-in observer; no default clicks and no provider calls.
Private HTML/secret never enters canonical AUD metadata or scoring. Sidecars
are opt-in, outside the sealed AUD, verified against the finished capture.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Lock
from typing import Any
from urllib.parse import urlsplit

from rasai.same_sample_observation import LiveWitness, verify_bound_live_witness

_LOCK = Lock()
_pending: dict[str, Any] | None = None
_captured: dict[str, list[tuple[LiveWitness, bytes, str]]] = {}
_MAX_CAPTURE = 2
_MAX_SIDECAR_BYTES = 4 * 1024 * 1024
_HOSTILE = re.compile(r"[\x00-\x1f\x7f]")
_ALLOWED_DEVICES = {"MOBILE", "DESKTOP"}


def _url(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or _HOSTILE.search(value):
        raise ValueError("FAQ URL not verified")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or len(value) > 2048
        or parsed.fragment
    ):
        raise ValueError("FAQ exact URL must be public HTTP(S) without credentials/fragment")
    return value


def configure_one_shot_faq(
    *, requested_url: str, allowed_final_url: str, device: str,
    target_id: str, collector_id: str, trusted_key_file: Path,
    explicit_operator_consent: bool = False,
    operator_network_boundary_acknowledged: bool = False,
) -> None:
    global _pending
    from rasai.faq_observation import _FAQ_CONTEXT
    if explicit_operator_consent is not True:
        raise ValueError("operator must explicitly consent to one FAQ gesture")
    if operator_network_boundary_acknowledged is not True:
        raise ValueError("network containment must be separately acknowledged")
    # Acknowledgment is an operator assertion, NOT proof of OS-level isolation.
    _url(requested_url)
    _url(allowed_final_url)
    if (
        device not in _ALLOWED_DEVICES
        or not isinstance(target_id, str) or len(target_id) > 256
        or not _FAQ_CONTEXT.search(target_id) or _HOSTILE.search(target_id)
        or not isinstance(collector_id, str) or not 1 <= len(collector_id) <= 128
        or _HOSTILE.search(collector_id)
    ):
        raise ValueError("invalid FAQ target/device/collector consent")
    path = Path(trusted_key_file)
    if path.is_symlink() or not path.is_file() or path.stat().st_size not in range(32, 129):
        raise ValueError("trusted local collector key file is missing or unsafe")
    # Never record key bytes in AUD, logs, published sidecar or CLI help.
    key = path.read_bytes()
    if len(key) < 32:
        raise ValueError("insufficient collector signing key")
    policy = {
        "requested_url": requested_url, "allowed_final_url": allowed_final_url,
        "device": device, "target_id": target_id, "collector_id": collector_id,
        "trusted_key": key,
        "operator_network_boundary_acknowledged": True,
        "network_containment_independently_verified": False,
    }
    with _LOCK:
        if _pending is not None:
            raise ValueError("FAQ gesture already configured for this execution")
        _pending = policy


def claim_for_snapshot(
    *, audit_id: str, page_id: str, requested_url: str,
    device: str, snapshot_id: str,
) -> dict[str, Any] | None:
    """Consume one matching policy; all other pages use canonical no-click path."""
    global _pending
    with _LOCK:
        policy = _pending
        if (policy is None or policy["requested_url"] != requested_url
                or policy["device"] != device):
            return None
        _pending = None
        return {
            **policy, "audit_id": audit_id, "page_id": page_id,
            "snapshot_id": snapshot_id,
            "sample_id": "M3-" + snapshot_id,
            "context_id": "CTX-" + snapshot_id,
        }


def abort_pending_faq() -> None:
    global _pending
    with _LOCK:
        _pending = None


def isolated_worker_faq_observer(policy: dict[str, Any]):
    """Called from the trusted Chromium worker; no site-supplied policy."""
    from rasai.same_sample_observation import observe_same_browser_sample

    def observe(*, page: Any, captured_html_sha256: str,
                requested_url: str, final_url: str, device: str,
                navigation_started_monotonic_ns: int, load_ms: float) -> dict[str, Any]:
        if (
            requested_url != policy["requested_url"]
            or final_url != policy["allowed_final_url"]
            or device != policy["device"]
        ):
            return {"status": "FAQ_EXPLICIT_SCOPE_MISMATCH"}
        identity = {
            key: policy[key] for key in (
                "audit_id", "page_id", "snapshot_id", "sample_id", "context_id",
                "requested_url", "device",
            )
        }
        identity["final_url"] = final_url
        identity["architecture"] = "UNKNOWN"
        witness = observe_same_browser_sample(
            page, scope=identity,
            navigation_started_monotonic_ns=navigation_started_monotonic_ns,
            load_ms=load_ms, faq_target_id=policy["target_id"],
            captured_dom_sha256=captured_html_sha256,
            signing_key=policy["trusted_key"],
            collector_id=policy["collector_id"],
            trusted_collectors=frozenset({policy["collector_id"]}),
            explicit_faq_opt_in=True,
            isolated_context_acknowledged=True,
            readiness_opt_in=False,
        )
        return {
            "status": witness.faq_result["status"],
            "before_sha256": witness.faq_result.get("before_sha256", ""),
            "after_sha256": witness.faq_result.get("after_sha256", ""),
            "_private_witness": witness,
        }
    return observe


def keep_private_witness(
    *, audit_id: str, witness: LiveWitness | None,
    trusted_key: bytes, collector_id: str,
) -> None:
    if not isinstance(witness, LiveWitness) or witness.scope["audit_id"] != audit_id:
        return
    with _LOCK:
        rows = _captured.setdefault(audit_id, [])
        if len(rows) < _MAX_CAPTURE:
            rows.append((witness, trusted_key, collector_id))


def discard_private_witness(audit_id: str | None = None) -> None:
    with _LOCK:
        if audit_id is None:
            _captured.clear()
        else:
            _captured.pop(audit_id, None)


def _sidecar_payload(
    witness: LiveWitness, verdict: dict[str, Any],
) -> bytes:
    return (
        json.dumps({
            "contract_version": "RASAI-FAQ-SAME-SAMPLE-SIDECAR-001",
            "scope": witness.scope,
            "receipt": witness.receipt,
            "receipt_mac": witness.receipt_mac,
            "signed_witness": witness.signed_witness,
            "witness_mac": witness.witness_mac,
            "later_html": witness.later_html,
            "verification": verdict,
            "advisory_only": True,
            "same_persisted_browser_session_independently_attested": False,
            "crawler_discovery_verified": False,
            "score_change_authorized": False,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
           allow_nan=False) + "\n"
    ).encode("utf-8")


def publish_faq_after_seal(*, audit_id: str, aud_dir: Path) -> dict[str, int]:
    """Independent read-only AUD cross-check then atomic immutable sidecar."""
    with _LOCK:
        rows = tuple(_captured.pop(audit_id, ()))
    status = {"eligible": len(rows), "published": 0, "rejected": 0, "rejection_reasons": []}
    if not rows:
        return status
    from rasai.apdex_readiness_sidecar import _original
    root = Path(aud_dir)
    try:
        original_id, _, _ = _original(root)
        if original_id != audit_id:
            raise ValueError("physical source ID mismatch")
        folder = root.parent / ".rasai-faq-sidecars" / audit_id
        if folder.parent.is_symlink() or folder.is_symlink():
            raise ValueError("unsafe FAQ sidecar path")
        for witness, key, collector_id in rows:
            try:
                verdict = verify_bound_live_witness(
                    witness, aud_dir=root, trusted_key=key,
                    permitted_collector_ids=frozenset({collector_id}),
                )
                if not verdict.get("signed_live_page_witness_valid"):
                    raise ValueError("SIGNED_WITNESS_INVALID:" + str(verdict.get("reason", "UNSPECIFIED")))
                if not verdict.get("persisted_dom_bytes_match_signed_receipt"):
                    raise ValueError("PERSISTED_DOM_NOT_ATTRIBUTABLE")
                payload = _sidecar_payload(witness, verdict)
                if len(payload) > _MAX_SIDECAR_BYTES:
                    raise ValueError("FAQ evidence exceeds bounded output")
                folder.mkdir(parents=True, exist_ok=True)
                dest = folder / (sha256(payload).hexdigest() + ".json")
                if dest.is_symlink():
                    raise ValueError("unsafe sidecar")
                import tempfile
                fd, name = tempfile.mkstemp(prefix=".pending-", dir=folder)
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(payload)
                        handle.flush()
                        os.fsync(handle.fileno())
                    try:
                        os.link(name, dest)
                    except FileExistsError:
                        if dest.is_symlink() or dest.read_bytes() != payload:
                            raise ValueError("sidecar replay mismatch")
                finally:
                    Path(name).unlink(missing_ok=True)
                status["published"] += 1
            except (OSError, ValueError, TypeError, KeyError) as exc:
                status["rejected"] += 1
                # Only bounded, allowlisted classifications leave this trust boundary.
                reason = str(exc) if type(exc) is ValueError else type(exc).__name__
                allowed = {"PERSISTED_DOM_NOT_ATTRIBUTABLE", "UNSPECIFIED"}
                if reason.startswith("SIGNED_WITNESS_INVALID:"):
                    reason = "SIGNED_WITNESS_INVALID"
                elif reason not in allowed:
                    reason = "SIDECAR_PUBLICATION_REJECTED"
                status["rejection_reasons"].append(reason)
    except (OSError, ValueError, TypeError):
        status["rejected"] = len(rows)
        status["rejection_reasons"] = ["AUD_SEAL_NOT_VERIFIED"]
    return status


__all__ = [
    "configure_one_shot_faq", "claim_for_snapshot", "abort_pending_faq",
    "isolated_worker_faq_observer", "keep_private_witness",
    "discard_private_witness", "publish_faq_after_seal",
]
