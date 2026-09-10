"""External identity links for the RASAi control plane.

The directory maps an identity provider's stable ``issuer + subject`` pair to the
internal ``USR-*`` identity used by authorization. It deliberately does not create
users or memberships during authentication.

SQLite gets the additive table lazily because local schema extensions are managed by
the application. PostgreSQL remains migration-governed and therefore must already
contain the table before this directory is used.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any
from urllib.parse import urlsplit

from .store import new_id, utc_now


@dataclass(frozen=True, slots=True)
class ExternalIdentity:
    external_identity_id: str
    user_id: str
    issuer: str
    subject: str
    email: str | None
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_issuer(value: str) -> str:
    issuer = value.strip()
    if not issuer or len(issuer) > 2048:
        raise ValueError("identity issuer must be a non-empty URL")
    parts = urlsplit(issuer)
    if parts.scheme != "https" or not parts.hostname or parts.fragment:
        raise ValueError("identity issuer must be an absolute HTTPS URL without fragment")
    return issuer.rstrip("/")


def normalize_subject(value: str) -> str:
    subject = value.strip()
    if not subject or len(subject) > 512:
        raise ValueError("identity subject must contain between 1 and 512 characters")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in subject):
        raise ValueError("identity subject cannot contain control characters")
    return subject


class IdentityDirectory:
    """Small persistence facade over a canonical platform store."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self.connection = store._connection  # canonical extension boundary
        if getattr(store, "backend", "sqlite") != "postgresql":
            self._ensure_sqlite_schema()

    def _ensure_sqlite_schema(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS external_identities (
                    external_identity_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    issuer TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(issuer, subject)
                );
                CREATE INDEX IF NOT EXISTS idx_external_identity_user
                    ON external_identities(user_id, issuer);
                """
            )
            self.connection.execute(
                """INSERT INTO platform_extension_meta(key,value) VALUES('identity_schema','1')
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value"""
            )

    @staticmethod
    def _item(row: Any) -> ExternalIdentity:
        return ExternalIdentity(
            external_identity_id=str(row["external_identity_id"]),
            user_id=str(row["user_id"]),
            issuer=str(row["issuer"]),
            subject=str(row["subject"]),
            email=str(row["email"]) if row["email"] is not None else None,
            created_at=str(row["created_at"]),
        )

    def link(
        self,
        *,
        user_id: str,
        issuer: str,
        subject: str,
        email: str | None = None,
    ) -> ExternalIdentity:
        normalized_issuer = normalize_issuer(issuer)
        normalized_subject = normalize_subject(subject)
        normalized_email = email.strip().casefold() if email and email.strip() else None
        user = self.connection.execute(
            "SELECT user_id,status FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if user is None:
            raise KeyError(f"user not found: {user_id}")
        if str(user["status"]).upper() != "ACTIVE":
            raise ValueError("external identity can only be linked to an active user")
        existing = self.connection.execute(
            "SELECT * FROM external_identities WHERE issuer=? AND subject=?",
            (normalized_issuer, normalized_subject),
        ).fetchone()
        if existing is not None:
            item = self._item(existing)
            if item.user_id != user_id:
                raise ValueError("external identity is already linked to a different RASAi user")
            if normalized_email != item.email:
                with self.connection:
                    self.connection.execute(
                        "UPDATE external_identities SET email=? WHERE external_identity_id=?",
                        (normalized_email, item.external_identity_id),
                    )
                existing = self.connection.execute(
                    "SELECT * FROM external_identities WHERE external_identity_id=?",
                    (item.external_identity_id,),
                ).fetchone()
                assert existing is not None
                return self._item(existing)
            return item
        item = ExternalIdentity(
            external_identity_id=new_id("IDN"),
            user_id=user_id,
            issuer=normalized_issuer,
            subject=normalized_subject,
            email=normalized_email,
            created_at=utc_now(),
        )
        with self.connection:
            self.connection.execute(
                """INSERT INTO external_identities(
                    external_identity_id,user_id,issuer,subject,email,created_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    item.external_identity_id,
                    item.user_id,
                    item.issuer,
                    item.subject,
                    item.email,
                    item.created_at,
                ),
            )
        return item

    def resolve_user_id(self, *, issuer: str, subject: str) -> str | None:
        normalized_issuer = normalize_issuer(issuer)
        normalized_subject = normalize_subject(subject)
        row = self.connection.execute(
            """SELECT e.user_id
               FROM external_identities e
               JOIN users u ON u.user_id=e.user_id
               WHERE e.issuer=? AND e.subject=? AND u.status='ACTIVE'""",
            (normalized_issuer, normalized_subject),
        ).fetchone()
        return str(row[0]) if row is not None else None

    def list(self, *, user_id: str | None = None) -> tuple[ExternalIdentity, ...]:
        if user_id:
            rows = self.connection.execute(
                "SELECT * FROM external_identities WHERE user_id=? ORDER BY issuer,subject",
                (user_id,),
            )
        else:
            rows = self.connection.execute(
                "SELECT * FROM external_identities ORDER BY user_id,issuer,subject"
            )
        return tuple(self._item(row) for row in rows)

    def unlink(self, external_identity_id: str) -> bool:
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM external_identities WHERE external_identity_id=?",
                (external_identity_id,),
            )
        return cursor.rowcount == 1
