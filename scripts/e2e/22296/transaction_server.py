"""Disposable HTTP instrumentation; never imported by the production app."""
# ruff: noqa: E402
# Guard fixture settings and initialize local JWT keys before importing the app.
import asyncio
import contextvars
import os
from pathlib import Path
from uuid import UUID

from runtime import guard

guard()
from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
load_and_validate_key_configuration()
from main import app
from infrastructure.cache.redis_client import startup_redis
from fastapi import HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from infrastructure.database import AsyncSessionLocal
from infrastructure.models.document_registry import reference_documents
from infrastructure.repositories import document_registry_repository as repo
from application.commands.document_registry import documents as commands
from application.queries.document_registry import views as registry_views
from application.queries.monetization import views as monetization_views

PREFIX = "22296-audit-tx"
CONTROL = Path(os.environ["REGISTRY_TX_CONTROL_FILE"]).read_text()
phase = contextvars.ContextVar("registry_tx_phase", default="")
target = contextvars.ContextVar("registry_tx_target", default="")
barriers = {}
faults = []


@app.middleware("http")
async def set_phase(request: Request, call_next):
    await startup_redis()
    allowed = request.headers.get("X-Audit-Tx-Key") == CONTROL
    token = phase.set(request.headers.get("X-Audit-Tx-Phase", "") if allowed else "")
    doc_token = target.set(request.headers.get("X-Audit-Tx-Document", "") if allowed else "")
    try:
        return await call_next(request)
    finally:
        phase.reset(token)
        target.reset(doc_token)


async def pause(document_id):
    barrier = barriers.get(str(document_id))
    if barrier is None:
        raise RuntimeError("Only explicitly armed owned fixtures may be paused")
    barrier["reached"] += 1
    await asyncio.wait_for(barrier["release"].wait(), timeout=45)


original_project = repo.project_documents
async def project_with_barrier(session, rows, today):
    if phase.get() == "pause_projection" and any(str(row["id"]) == target.get() for row in rows):
        await pause(target.get())
    return await original_project(session, rows, today)
repo.project_documents = project_with_barrier


def instrument_actor(original):
    async def wrapped(*args, **kwargs):
        actor = await original(*args, **kwargs)
        if phase.get() == "pause_actor":
            await pause(target.get())
        return actor
    return wrapped

registry_views.resolve_actor = instrument_actor(registry_views.resolve_actor)
monetization_views.resolve_actor = instrument_actor(monetization_views.resolve_actor)

original_lock = repo.lock_documents
async def observed_write_lock(session, document_ids):
    if phase.get() == "observe_write_lock" and target.get() in {str(identifier) for identifier in document_ids}:
        barrier = barriers[target.get()]
        barrier["writer_pid"] = await session.scalar(text("SELECT pg_backend_pid()"))
    return await original_lock(session, document_ids)
repo.lock_documents = observed_write_lock

original_store = commands._store_version
async def store_owned(session, document_id, payload, uploads, prepared, actor, storage, keys, company_rows, retained):
    fault = phase.get()
    if fault in {"commit_ack_loss", "before_commit_failure"}:
        if not payload["name"].startswith(PREFIX) or not uploads or not all(upload.filename.startswith(PREFIX) for upload in uploads):
            raise RuntimeError("Refusing to fault another fixture")
        session.info["registry_tx_commit"] = str(document_id)
    result = await original_store(session, document_id, payload, uploads, prepared, actor, storage, keys, company_rows, retained)
    if fault == "before_commit_failure":
        faults.append({"document_id": str(document_id), "before_commit": True})
        raise RuntimeError("22296 intentional failure after real S3 and SQL, before commit")
    return result
commands._store_version = store_owned

original_commit = AsyncSession.commit
async def commit_with_ack_loss(session):
    own_id = session.info.pop("registry_tx_commit", None)
    await original_commit(session)
    if own_id is not None and phase.get() == "commit_ack_loss":
        faults.append({"document_id": own_id, "real_commit_returned": True})
        raise ConnectionError("22296 injected lost commit acknowledgement")
AsyncSession.commit = commit_with_ack_loss


@app.get("/__registry_tx/control")
async def control(request: Request, action: str, document_id: UUID | None = None):
    if request.headers.get("X-Audit-Tx-Key") != CONTROL:
        raise HTTPException(403)
    if action == "faults":
        return {"faults": faults}
    if document_id is None:
        raise HTTPException(422)
    key = str(document_id)
    if action == "arm":
        async with AsyncSessionLocal() as session:
            number = await session.scalar(select(reference_documents.c.contract_number).where(reference_documents.c.id == document_id))
        if not number or not number.startswith(PREFIX):
            raise HTTPException(403, "Not this test's fixture")
        barriers[key] = {"reached": 0, "release": asyncio.Event()}
        return {"armed": True}
    barrier = barriers.get(key)
    if barrier is None:
        raise HTTPException(404)
    if action == "release":
        barrier["release"].set()
    waiting = False
    if "writer_pid" in barrier:
        async with AsyncSessionLocal() as session:
            waiting = await session.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid = :pid"), {"pid": barrier["writer_pid"]})
    return {"reached": barrier["reached"], "released": barrier["release"].is_set(), "writer_waiting_for_lock": bool(waiting)}
