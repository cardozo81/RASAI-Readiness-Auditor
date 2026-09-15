"""Apply versioned task profiles without changing provider routing or normative contracts."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
import re
from types import MethodType
from typing import Any, Callable, Iterable, Mapping

from rasai.ai_task_profiles import (
    IMPROVEMENT_DOMAIN_PROFILES,
    active_task_profile_catalog,
    profile_identity,
    profile_summary_tag,
    profiles_for_improvement_domains,
    render_task_profiles,
)

_INSTALLED = False
_PROFILE_MARKER = "Task specialization profile:"
_PROFILE_TAG_RE = re.compile(r"(?:^|;)profile=([^;]+)")


def _current_improvement_profiles() -> tuple[str, ...]:
    raw = str(os.environ.get("RASAI_IMPROVEMENT_DOMAINS") or "").strip()
    if raw:
        domains = [value.strip().upper() for value in raw.replace(";", ",").split(",") if value.strip()]
    else:
        domains = list(IMPROVEMENT_DOMAIN_PROFILES)
    return profiles_for_improvement_domains(domains)


def _prefix(text: str, profile_ids: str | Iterable[str]) -> str:
    if _PROFILE_MARKER in text:
        return text
    return render_task_profiles(profile_ids).rstrip() + "\n\n" + text.lstrip()


def _inject_payload(payload: Any, profile_ids: str | Iterable[str]) -> Any:
    if not isinstance(payload, Mapping):
        return payload
    updated = dict(payload)
    if isinstance(updated.get("instructions"), str):
        updated["instructions"] = _prefix(str(updated["instructions"]), profile_ids)
        return updated
    if isinstance(updated.get("system"), str):
        updated["system"] = _prefix(str(updated["system"]), profile_ids)
        return updated
    if isinstance(updated.get("prompt"), str):
        updated["prompt"] = _prefix(str(updated["prompt"]), profile_ids)
        return updated
    messages = updated.get("messages")
    if isinstance(messages, list):
        replaced_messages: list[Any] = []
        applied = False
        for raw in messages:
            if not isinstance(raw, Mapping):
                replaced_messages.append(raw)
                continue
            item = dict(raw)
            if not applied and str(item.get("role") or "").casefold() == "system" and isinstance(item.get("content"), str):
                item["content"] = _prefix(str(item["content"]), profile_ids)
                applied = True
            replaced_messages.append(item)
        if applied:
            updated["messages"] = replaced_messages
            return updated
    if isinstance(updated.get("input"), str):
        updated["input"] = _prefix(str(updated["input"]), profile_ids)
        return updated
    return updated


def _tag_attempt(attempt: Any, profile_ids: str | Iterable[str], *, request_hash: str | None = None) -> Any:
    if attempt is None:
        return attempt
    summary = str(getattr(attempt, "request_message_summary", "") or "")
    tag = profile_summary_tag(profile_ids)
    if not _PROFILE_TAG_RE.search(summary):
        summary = (summary.rstrip(";") + ";" if summary else "") + tag
    updates: dict[str, Any] = {"request_message_summary": summary}
    if request_hash is not None:
        updates["request_payload_hash"] = request_hash
    try:
        return replace(attempt, **updates)
    except TypeError:
        return attempt


def _existing_profile_identity(summary: str) -> tuple[str, str] | None:
    match = _PROFILE_TAG_RE.search(summary)
    if not match:
        return None
    ids: list[str] = []
    versions: list[str] = []
    for token in match.group(1).split(","):
        profile_id, separator, version = token.strip().partition("@")
        if not separator or not profile_id or not version:
            continue
        ids.append(profile_id)
        versions.append(version)
    if not ids:
        return None
    return ",".join(ids), ",".join(versions)


def _infer_profiles(attempt: Any) -> tuple[str, ...]:
    summary = str(getattr(attempt, "request_message_summary", "") or "")
    identity = _existing_profile_identity(summary)
    if identity is not None:
        return tuple(value for value in identity[0].split(",") if value)
    contract = str(getattr(attempt, "semantic_contract_version", "") or "").upper()
    text = (summary + ";" + contract).upper()
    if "CONTENT-REMEDIATION" in text:
        return ("CONTENT_REMEDIATION",)
    if "SOURCE-QUALITY" in text:
        return ("SOURCE_QUALITY",)
    if "TECHNICAL-REMEDIATION" in text or "CRAWLING" in text:
        return ("CRAWL_DISCOVERY",)
    if "IMPROVEMENT" in text:
        return _current_improvement_profiles()
    if "COMPETITIVE" in text or "SEARCH-INTELLIGENCE" in text:
        return ("SEARCH_INTELLIGENCE",)
    if "CONSOLIDATED" in text or "EVOLUTION" in text:
        return ("EVOLUTION",)
    if "SEMANTIC" in text:
        return ("SEMANTIC_READINESS",)
    return ()


def _patch_instruction_function(
    module: Any,
    name: str,
    resolver: Callable[..., str | Iterable[str]],
) -> None:
    original = getattr(module, name, None)
    marker = f"_rasai_task_profiles_{name}"
    if not callable(original) or getattr(module, marker, False):
        return

    def profiled(*args: Any, **kwargs: Any) -> Any:
        value = original(*args, **kwargs)
        if not isinstance(value, str):
            return value
        return _prefix(value, resolver(*args, **kwargs))

    setattr(module, name, profiled)
    setattr(module, marker, True)


def _patch_request_method(cls: Any, profile_ids: str | Iterable[str]) -> None:
    original = getattr(cls, "_request_payload", None)
    marker = "_rasai_task_profiles_request_payload"
    if not callable(original) or getattr(cls, marker, False):
        return

    def request_payload(self: Any, *args: Any, **kwargs: Any) -> Any:
        return _inject_payload(original(self, *args, **kwargs), profile_ids)

    cls._request_payload = request_payload
    setattr(cls, marker, True)


def _patch_semantic_profiles() -> None:
    from rasai import copilot_provider, m18_ai, openai_provider, provider_extensions, semantic

    _patch_request_method(semantic.OpenAIProvider, "SEMANTIC_READINESS")
    _patch_request_method(openai_provider.OpenAIProvider, "SEMANTIC_READINESS")
    _patch_request_method(m18_ai.ResponsesSemanticProvider, "SEMANTIC_READINESS")
    _patch_instruction_function(provider_extensions, "_semantic_instructions", lambda: "SEMANTIC_READINESS")
    _patch_instruction_function(copilot_provider, "_semantic_prompt", lambda _input: "SEMANTIC_READINESS")

    original_history = m18_ai.provider_attempt_history
    if not getattr(m18_ai, "_rasai_task_profiles_attempt_history", False):
        def provider_attempt_history(provider: Any):
            return tuple(_tag_attempt(item, "SEMANTIC_READINESS") for item in original_history(provider))
        m18_ai.provider_attempt_history = provider_attempt_history
        m18_ai._rasai_task_profiles_attempt_history = True


def _patch_content_profiles() -> None:
    from rasai import m20_ai, provider_extensions_m20, provider_runtime_policy

    _patch_instruction_function(provider_extensions_m20, "_instructions", lambda: "CONTENT_REMEDIATION")

    original_once = m20_ai.ContentRemediationProvider._analyze_once
    if not getattr(m20_ai.ContentRemediationProvider, "_rasai_task_profiles_analyze_once", False):
        def analyze_once(self: Any, request: Any):
            original_transport = self._transport
            actual_hash: str | None = None

            def transport(url: str, headers: dict[str, str], body: bytes, timeout: float):
                nonlocal actual_hash
                try:
                    payload = json.loads(body.decode("utf-8"))
                    modified = _inject_payload(payload, "CONTENT_REMEDIATION")
                    wire = json.dumps(modified, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                    wire = body
                actual_hash = hashlib.sha256(wire).hexdigest()
                return original_transport(url, headers, wire, timeout)

            self._transport = transport
            try:
                result = original_once(self, request)
            finally:
                self._transport = original_transport
            if getattr(self, "_last_attempt", None) is not None:
                self._last_attempt = _tag_attempt(
                    self._last_attempt,
                    "CONTENT_REMEDIATION",
                    request_hash=actual_hash,
                )
            return result

        m20_ai.ContentRemediationProvider._analyze_once = analyze_once
        m20_ai.ContentRemediationProvider._rasai_task_profiles_analyze_once = True

    original_patch_reasoning = provider_runtime_policy._patch_content_provider_reasoning
    if not getattr(provider_runtime_policy, "_rasai_task_profiles_content_reasoning", False):
        def patch_content_provider_reasoning(provider: Any) -> None:
            original_patch_reasoning(provider)
            request_method = getattr(provider, "_request_payload", None)
            if not callable(request_method) or getattr(provider, "_rasai_task_profiles_content_request", False):
                return

            def request_payload(_self: Any, request: Any):
                return _inject_payload(request_method(request), "CONTENT_REMEDIATION")

            provider._request_payload = MethodType(request_payload, provider)
            provider._rasai_task_profiles_content_request = True

        provider_runtime_policy._patch_content_provider_reasoning = patch_content_provider_reasoning
        provider_runtime_policy._rasai_task_profiles_content_reasoning = True


def _wrap_candidate_call(module: Any, function_name: str, profile_ids: str | Iterable[str]) -> None:
    original = getattr(module, function_name, None)
    marker = f"_rasai_task_profiles_{function_name}"
    if not callable(original) or getattr(module, marker, False):
        return

    def profiled(candidate: Any, *args: Any, **kwargs: Any):
        original_transport = getattr(candidate, "_transport", None)
        if not callable(original_transport):
            result = original(candidate, *args, **kwargs)
            if isinstance(result, tuple) and len(result) == 2:
                return result[0], _tag_attempt(result[1], profile_ids)
            return result
        actual_hash: str | None = None

        def transport(url: str, headers: dict[str, str], body: bytes, timeout: float):
            nonlocal actual_hash
            try:
                payload = json.loads(body.decode("utf-8"))
                modified = _inject_payload(payload, profile_ids)
                wire = json.dumps(modified, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                wire = body
            actual_hash = hashlib.sha256(wire).hexdigest()
            return original_transport(url, headers, wire, timeout)

        candidate._transport = transport
        try:
            result = original(candidate, *args, **kwargs)
        finally:
            candidate._transport = original_transport
        if isinstance(result, tuple) and len(result) == 2:
            return result[0], _tag_attempt(result[1], profile_ids, request_hash=actual_hash)
        return result

    setattr(module, function_name, profiled)
    setattr(module, marker, True)


def _patch_specialist_profiles() -> None:
    from rasai import ai_orchestration_unification, improvement_intelligence, m24_ai, source_quality_ai
    from rasai.consolidation import specialist

    _wrap_candidate_call(source_quality_ai, "_call", "SOURCE_QUALITY")
    _wrap_candidate_call(m24_ai, "_call", "CRAWL_DISCOVERY")

    _patch_instruction_function(
        improvement_intelligence,
        "_instructions",
        lambda _language, domains: profiles_for_improvement_domains(domains),
    )
    _patch_instruction_function(specialist, "_instructions", lambda: "EVOLUTION")

    original_structured = ai_orchestration_unification._structured_payload
    if not getattr(ai_orchestration_unification, "_rasai_task_profiles_structured_payload", False):
        def structured_payload(provider: Any, *, schema_name: str, instructions: str, user_text: str, schema: dict[str, Any]):
            lowered = schema_name.casefold()
            if "competitive" in lowered:
                instructions = _prefix(instructions, "SEARCH_INTELLIGENCE")
            elif "improvement" in lowered:
                instructions = _prefix(instructions, _current_improvement_profiles())
            elif "source_quality" in lowered or "source-quality" in lowered:
                instructions = _prefix(instructions, "SOURCE_QUALITY")
            return original_structured(
                provider,
                schema_name=schema_name,
                instructions=instructions,
                user_text=user_text,
                schema=schema,
            )

        ai_orchestration_unification._structured_payload = structured_payload
        ai_orchestration_unification._rasai_task_profiles_structured_payload = True

    original_attempt = ai_orchestration_unification._attempt
    if not getattr(ai_orchestration_unification, "_rasai_task_profiles_attempt", False):
        def attempt(*args: Any, **kwargs: Any):
            item = original_attempt(*args, **kwargs)
            profiles = _infer_profiles(item)
            return _tag_attempt(item, profiles) if profiles else item
        ai_orchestration_unification._attempt = attempt
        ai_orchestration_unification._rasai_task_profiles_attempt = True

    original_record = specialist._attempt_record
    if not getattr(specialist, "_rasai_task_profiles_attempt_record", False):
        def attempt_record(*args: Any, **kwargs: Any):
            return _tag_attempt(original_record(*args, **kwargs), "EVOLUTION")
        specialist._attempt_record = attempt_record
        specialist._rasai_task_profiles_attempt_record = True


def _install_profile_metadata_table(connection: Any) -> None:
    with connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_task_profile_attempts (
                attempt_id TEXT PRIMARY KEY,
                audit_id TEXT NOT NULL,
                source_table TEXT NOT NULL,
                request_payload_hash TEXT,
                task_profile_id TEXT NOT NULL,
                task_profile_version TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_task_profile_attempts_audit ON ai_task_profile_attempts(audit_id,source_table)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_task_profile_attempts_hash ON ai_task_profile_attempts(audit_id,request_payload_hash)"
        )


def _patch_persistence() -> None:
    from rasai import m18_persistence, m20_persistence

    for persistence_class, source_table in (
        (m18_persistence.M18Persistence, "ai_provider_attempts"),
        (m20_persistence.M20Persistence, "content_remediation_attempts"),
    ):
        marker = "_rasai_task_profiles_persistence"
        if getattr(persistence_class, marker, False):
            continue
        original_initialize = persistence_class._initialize
        original_add = persistence_class.add_attempt

        def initialize(self: Any, _original: Callable[..., Any] = original_initialize) -> None:
            _original(self)
            _install_profile_metadata_table(self._connection)

        def add_attempt(
            self: Any,
            *,
            attempt_id: str,
            audit_id: str,
            attempt: Any,
            _original: Callable[..., Any] = original_add,
            _source_table: str = source_table,
            **kwargs: Any,
        ) -> None:
            profiles = _infer_profiles(attempt)
            tagged = _tag_attempt(attempt, profiles) if profiles else attempt
            _original(
                self,
                attempt_id=attempt_id,
                audit_id=audit_id,
                attempt=tagged,
                **kwargs,
            )
            if not profiles:
                return
            ids, versions = profile_identity(profiles)
            with self._connection:
                self._connection.execute(
                    """
                    INSERT OR REPLACE INTO ai_task_profile_attempts (
                        attempt_id,audit_id,source_table,request_payload_hash,
                        task_profile_id,task_profile_version
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attempt_id,
                        audit_id,
                        _source_table,
                        getattr(tagged, "request_payload_hash", None),
                        ids,
                        versions,
                    ),
                )

        persistence_class._initialize = initialize
        persistence_class.add_attempt = add_attempt
        setattr(persistence_class, marker, True)


def _patch_ai_usage_projection() -> None:
    try:
        from rasai import report_ai_runtime_enrichment as report
    except ImportError:
        return
    if getattr(report, "_rasai_task_profiles_exchange_rows", False):
        return
    original_rows = report._exchange_rows

    def exchange_rows(connection: Any, audit_id: str):
        rows = original_rows(connection, audit_id)
        if not rows:
            return rows
        try:
            metadata = connection.execute(
                """
                SELECT request_payload_hash,task_profile_id,task_profile_version
                FROM ai_task_profile_attempts
                WHERE audit_id=? AND request_payload_hash IS NOT NULL
                ORDER BY rowid
                """,
                (audit_id,),
            ).fetchall()
        except Exception:
            return rows
        by_hash: dict[str, tuple[str, str]] = {}
        for row in metadata:
            digest = str(row["request_payload_hash"] or "")
            if digest and digest not in by_hash:
                by_hash[digest] = (
                    str(row["task_profile_id"] or ""),
                    str(row["task_profile_version"] or ""),
                )
        output: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            identity = by_hash.get(str(item.get("request_sha256") or ""))
            if identity and identity[0]:
                purpose = str(item.get("purpose") or "IA")
                item["purpose"] = f"{purpose} · Perfil {identity[0]} v{identity[1]}"
            output.append(item)
        return output

    report._exchange_rows = exchange_rows
    report._rasai_task_profiles_exchange_rows = True


def install() -> None:
    """Install task-profile application after provider/runtime composition is complete."""
    global _INSTALLED
    if _INSTALLED:
        return
    # Fail early on malformed operator configuration before any paid provider call.
    active_task_profile_catalog()
    _patch_semantic_profiles()
    _patch_content_profiles()
    _patch_specialist_profiles()
    _patch_persistence()
    _patch_ai_usage_projection()
    _INSTALLED = True
