"""Real HTTP save/refresh concurrency with PostgreSQL row-lock timing only."""
from __future__ import annotations

import asyncio
import json
from time import monotonic
from uuid import UUID

from sqlalchemy import select, text

from acceptance import API, ROOT, db_questionnaire, guard, progress, require
from core_acceptance import projection_application


async def verify():
    guard()
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import ApplicationQuestionnaire, LeasingApplication

    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    app_id = await projection_application(api, state)
    path = f"/api/v1/questionnaire/{app_id}"
    await api.request("client", "PUT", path, json={"company_email": "before@example.test"})
    before = await db_questionnaire(app_id)
    jobs = []
    async with AsyncSessionLocal() as application_barrier, AsyncSessionLocal() as questionnaire_barrier, AsyncSessionLocal() as observer:
        await application_barrier.execute(select(LeasingApplication.id).where(LeasingApplication.id == UUID(app_id)).with_for_update())
        application_pid = await application_barrier.scalar(text("SELECT pg_backend_pid()"))
        await questionnaire_barrier.execute(select(ApplicationQuestionnaire.id).where(ApplicationQuestionnaire.application_id == UUID(app_id)).with_for_update())
        questionnaire_pid = await questionnaire_barrier.scalar(text("SELECT pg_backend_pid()"))

        async def blocked_pids(blockers, *, exclude=()):
            deadline = monotonic() + 12
            while monotonic() < deadline:
                # pg_stat_activity caches the backend list for this transaction;
                # a newly opened HTTP connection must be visible on the next poll.
                await observer.execute(text("SELECT pg_stat_clear_snapshot()"))
                rows = (await observer.execute(text("""
                    SELECT pid, pg_blocking_pids(pid) AS blockers
                    FROM pg_stat_activity
                    WHERE datname = current_database() AND wait_event_type = 'Lock'
                """))).mappings().all()
                matches = [row["pid"] for row in rows if row["pid"] not in exclude and set(row["blockers"]) & set(blockers)]
                if matches:
                    return matches
                await asyncio.sleep(0.03)
            raise AssertionError("HTTP transaction did not reach the intended PostgreSQL row-lock barrier")

        try:
            jobs.append(asyncio.create_task(api.request("client", "PUT", path,
                expected=(200, 500), raw=True, json={"company_email": "concurrent@example.test"})))
            save_pid = (await blocked_pids((application_pid, questionnaire_pid)))[0]
            jobs.append(asyncio.create_task(api.request("client", "POST", path + "/refresh",
                expected=(200, 500), raw=True)))
            refresh_pid = (await blocked_pids((application_pid, save_pid), exclude=(save_pid,)))[0]
            # Before the fix save holds questionnaire and waits for application;
            # refresh is ahead in the application's lock queue. After the fix
            # both wait for application before touching questionnaire.
            await questionnaire_barrier.rollback()
            await blocked_pids((application_pid, refresh_pid), exclude=(refresh_pid,))
            await application_barrier.rollback()
            responses = await asyncio.wait_for(asyncio.gather(*jobs), timeout=25)
            require([response.status_code for response in responses] == [200, 200],
                f"Concurrent save/refresh failed: save={responses[0].status_code}, refresh={responses[1].status_code}")
        finally:
            await questionnaire_barrier.rollback()
            await application_barrier.rollback()
            for job in jobs:
                if not job.done():
                    job.cancel()
            await asyncio.gather(*jobs, return_exceptions=True)
    after = (await api.request("client", "GET", path))["questionnaire"]
    require(after["id"] == str(before["id"]), "Concurrent operations replaced questionnaire")
    require(after["company_email"] == "concurrent@example.test", "Refresh lost the concurrent manual value")
    saved = await db_questionnaire(app_id)
    require(saved["field_sources"]["company_email"] == "manual", "Manual source was lost")
    require(saved["questionnaire_completed_at"] == before["questionnaire_completed_at"], "Refresh completed an undelivered questionnaire")
    progress("questionnaire_save_refresh_lock_order_passed", application_id=app_id, statuses=[200, 200])


if __name__ == "__main__":
    asyncio.run(verify())
