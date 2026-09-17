"""Lease renewal for long-running SaaS AUD jobs.

A governed audit may spend longer collecting external evidence before AI begins.  The
control-plane job remains one durable AUDIT unit, but a healthy worker renews its lease
periodically so crash recovery does not mistake legitimate long work for abandonment.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import threading
from typing import Any, Iterator


_INSTALLED = False


def _install_store_renewal() -> None:
    from rasai.platform.secure_store import SecurePlatformStore

    if hasattr(SecurePlatformStore, "renew_execution_job_lease"):
        return

    def renew_execution_job_lease(
        self: Any,
        job_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 300,
    ):
        if lease_seconds < 30 or lease_seconds > 86400:
            raise ValueError("lease_seconds must be between 30 and 86400")
        worker = str(worker_id).strip()
        if not worker:
            raise ValueError("worker_id cannot be empty")
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
        with self._connection:
            cursor = self._connection.execute(
                """UPDATE execution_jobs SET lease_until=?,updated_at=?
                   WHERE job_id=? AND status IN ('CLAIMED','RUNNING') AND claimed_by=?""",
                (lease_until, now, job_id, worker),
            )
        if cursor.rowcount != 1:
            raise ValueError("execution job is not active for this worker")
        item = self.get_execution_job(job_id)
        if item is None:
            raise KeyError(f"execution job not found: {job_id}")
        return item

    SecurePlatformStore.renew_execution_job_lease = renew_execution_job_lease


def _initial_lease_seconds(job: Any, fallback: int) -> int:
    text = str(getattr(job, "lease_until", "") or "").strip()
    if text:
        try:
            lease_until = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if lease_until.tzinfo is None:
                lease_until = lease_until.replace(tzinfo=UTC)
            remaining = int((lease_until.astimezone(UTC) - datetime.now(UTC)).total_seconds())
            if remaining >= 30:
                return min(max(remaining, 30), 86400)
        except (TypeError, ValueError, OverflowError):
            pass
    return min(max(int(fallback), 30), 86400)


@contextmanager
def _lease_heartbeat(
    *,
    audits_root: Any,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
) -> Iterator[None]:
    from rasai.platform.database import open_platform_store

    stop = threading.Event()
    failures: list[str] = []
    interval = max(10.0, min(60.0, float(lease_seconds) / 3.0))

    def heartbeat() -> None:
        while not stop.wait(interval):
            try:
                with open_platform_store(audits_root=audits_root) as heartbeat_store:
                    heartbeat_store.renew_execution_job_lease(
                        job_id,
                        worker_id,
                        lease_seconds=lease_seconds,
                    )
            except Exception as exc:
                # One transient renewal failure is not enough to abort useful work. Keep
                # retrying while the worker is alive; final completion still verifies
                # ownership via finish_execution_job.
                failures.append(f"{type(exc).__name__}:{str(exc)[:200]}")
                if len(failures) > 8:
                    del failures[:-8]

    thread = threading.Thread(
        target=heartbeat,
        name=f"rasai-lease-{job_id[:12]}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=max(1.0, min(5.0, interval)))


def _install_worker() -> None:
    from rasai import worker

    current = worker.run_one
    if getattr(current, "_rasai_lease_heartbeat", False):
        return

    def run_one(
        worker_id: str,
        *,
        audits_root: str = "audits",
        lease_seconds: int = 900,
    ):
        from rasai.platform.database import open_platform_store

        with open_platform_store(audits_root=audits_root) as store:
            if hasattr(store, "materialize_due_schedules"):
                store.materialize_due_schedules(limit=100)
            job = store.claim_execution_job(worker_id, lease_seconds=lease_seconds)
            if job is None:
                return None
            store.start_execution_job(job.job_id, worker_id)
            effective_lease = _initial_lease_seconds(job, lease_seconds)
            try:
                with _lease_heartbeat(
                    audits_root=audits_root,
                    job_id=job.job_id,
                    worker_id=worker_id,
                    lease_seconds=effective_lease,
                ):
                    result = worker.execute_job(store, job, audits_root=audits_root)
            except Exception as exc:
                return worker._finish(
                    store,
                    job.job_id,
                    worker_id,
                    succeeded=False,
                    error=worker.redact_text(str(exc)),
                )
            return worker._finish(
                store,
                job.job_id,
                worker_id,
                succeeded=True,
                result_ref=result.result_ref,
                result_metadata=result.metadata,
            )

    run_one._rasai_lease_heartbeat = True
    run_one._rasai_original = current
    worker.run_one = run_one


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _install_store_renewal()
    _install_worker()
    _INSTALLED = True


__all__ = ["install"]
