from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from rasai.platform.identity_directory import IdentityDirectory, normalize_issuer, normalize_subject
from rasai.platform.secure_store import SecurePlatformStore


def test_external_identity_is_explicit_stable_and_non_provisioning() -> None:
    with tempfile.TemporaryDirectory() as directory:
        store = SecurePlatformStore(Path(directory) / "platform.db")
        try:
            user_a = store.get_or_create_user("Analyst A", email="a@example.test")
            user_b = store.get_or_create_user("Analyst B", email="b@example.test")
            identities = IdentityDirectory(store)

            linked = identities.link(
                user_id=user_a.user_id,
                issuer="https://login.example.test/",
                subject="external-subject-123",
                email="A@EXAMPLE.TEST",
            )
            assert linked.issuer == "https://login.example.test"
            assert linked.email == "a@example.test"
            assert identities.resolve_user_id(
                issuer="https://login.example.test",
                subject="external-subject-123",
            ) == user_a.user_id

            same = identities.link(
                user_id=user_a.user_id,
                issuer="https://login.example.test",
                subject="external-subject-123",
                email="a@example.test",
            )
            assert same.external_identity_id == linked.external_identity_id

            with pytest.raises(ValueError, match="different RASAi user"):
                identities.link(
                    user_id=user_b.user_id,
                    issuer="https://login.example.test",
                    subject="external-subject-123",
                )

            assert identities.resolve_user_id(
                issuer="https://login.example.test",
                subject="unknown",
            ) is None
            assert identities.unlink(linked.external_identity_id)
            assert identities.resolve_user_id(
                issuer="https://login.example.test",
                subject="external-subject-123",
            ) is None
        finally:
            store.close()


def test_external_identity_validation_fails_closed() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        normalize_issuer("http://idp.example.test")
    with pytest.raises(ValueError, match="control"):
        normalize_subject("subject\nwith-control")
