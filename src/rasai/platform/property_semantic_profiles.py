"""Control-plane persistence for reusable property semantic profiles."""
from __future__ import annotations

from typing import Any

from rasai.property_semantic_profile import build_property_semantic_profile


_PROFILE_FIELDS = (
    "business_sector",
    "business_description",
    "primary_offering",
    "target_audience_profile",
    "primary_goal",
    "positioning",
)


class PropertySemanticProfileStoreMixin:
    """Backend-neutral CRUD over a dedicated property semantic-profile relation."""

    def _initialize_property_semantic_profiles_sqlite(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS property_semantic_profiles (
                    property_id TEXT PRIMARY KEY REFERENCES properties(property_id) ON DELETE CASCADE,
                    business_sector TEXT NOT NULL DEFAULT 'auto',
                    business_description TEXT NOT NULL DEFAULT 'auto',
                    primary_offering TEXT NOT NULL DEFAULT 'auto',
                    target_audience_profile TEXT NOT NULL DEFAULT 'auto',
                    primary_goal TEXT NOT NULL DEFAULT 'auto',
                    positioning TEXT NOT NULL DEFAULT 'auto',
                    revision INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL,
                    updated_by TEXT REFERENCES users(user_id) ON DELETE SET NULL
                )
                """
            )

    def get_property_semantic_profile(self, property_id: str) -> dict[str, Any]:
        # hierarchy_for_property is also the canonical existence check used by HTTP auth.
        self.hierarchy_for_property(property_id)
        row = self._connection.execute(
            "SELECT * FROM property_semantic_profiles WHERE property_id=?",
            (property_id,),
        ).fetchone()
        if row is None:
            profile = build_property_semantic_profile()
            return {
                "property_id": property_id,
                **profile.provider_payload(),
                "revision": 0,
                "updated_at": None,
                "updated_by": None,
            }
        profile = build_property_semantic_profile(
            business_sector=str(row["business_sector"]),
            business_description=str(row["business_description"]),
            primary_offering=str(row["primary_offering"]),
            target_audience_profile=str(row["target_audience_profile"]),
            primary_goal=str(row["primary_goal"]),
            positioning=str(row["positioning"]),
        )
        return {
            "property_id": property_id,
            **profile.provider_payload(),
            "revision": int(row["revision"]),
            "updated_at": str(row["updated_at"]),
            "updated_by": str(row["updated_by"]) if row["updated_by"] else None,
        }

    def set_property_semantic_profile(
        self,
        property_id: str,
        *,
        business_sector: str = "auto",
        business_description: str = "auto",
        primary_offering: str = "auto",
        target_audience_profile: str = "auto",
        primary_goal: str = "auto",
        positioning: str = "auto",
        updated_by: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self.hierarchy_for_property(property_id)
        profile = build_property_semantic_profile(
            business_sector=business_sector,
            business_description=business_description,
            primary_offering=primary_offering,
            target_audience_profile=target_audience_profile,
            primary_goal=primary_goal,
            positioning=positioning,
        )
        current = self._connection.execute(
            "SELECT revision FROM property_semantic_profiles WHERE property_id=?",
            (property_id,),
        ).fetchone()
        current_revision = int(current["revision"]) if current is not None else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise ValueError(
                f"property semantic profile revision conflict: expected {expected_revision}, current {current_revision}"
            )
        revision = current_revision + 1
        from .store import utc_now

        now = utc_now()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO property_semantic_profiles(
                    property_id,business_sector,business_description,primary_offering,
                    target_audience_profile,primary_goal,positioning,revision,updated_at,updated_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(property_id) DO UPDATE SET
                    business_sector=excluded.business_sector,
                    business_description=excluded.business_description,
                    primary_offering=excluded.primary_offering,
                    target_audience_profile=excluded.target_audience_profile,
                    primary_goal=excluded.primary_goal,
                    positioning=excluded.positioning,
                    revision=excluded.revision,
                    updated_at=excluded.updated_at,
                    updated_by=excluded.updated_by
                """,
                (
                    property_id,
                    profile.business_sector,
                    profile.business_description,
                    profile.primary_offering,
                    profile.target_audience_profile,
                    profile.primary_goal,
                    profile.positioning,
                    revision,
                    now,
                    updated_by,
                ),
            )
        return self.get_property_semantic_profile(property_id)


def profile_payload_values(profile: dict[str, Any]) -> dict[str, str]:
    """Return only the six reusable semantic values, excluding control-plane metadata."""
    return {name: str(profile.get(name) or "auto") for name in _PROFILE_FIELDS}
