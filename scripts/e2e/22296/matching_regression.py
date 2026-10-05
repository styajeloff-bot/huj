"""Real HTTP coverage for positive OR matching and unchanged eligibility guards."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from runtime import API, ROOT, guard, pdf, progress, require

BASE = "/api/v1/document-registry"
PROGRAMS = "/api/v1/admin/monetization/programs"


async def main():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    day = datetime.now(ZoneInfo("Europe/Moscow")).date()
    prefix = "22296-match-" + uuid4().hex[:8]
    companies = state["companies"]
    catalog = state["catalog"]
    lc = companies["leasing"]["leasing_company_id"]
    lc2 = companies["leasing2"]["leasing_company_id"]
    dealer = companies["dealer"]["company_id"]
    distributor = companies["distributor"]["company_id"]
    mark = catalog["mark_id"]
    model = catalog["model_id"]
    roots = []
    deleted = set()
    checks = 0

    def check(label, condition):
        nonlocal checks
        checks += 1
        progress("matching_check", check=label, passed=bool(condition))
        require(condition, label)

    async def upload(label, participants, *, start=-1, end=90, group=None):
        body = {
            "document_type": "contract", "contract_number": prefix + "-" + label,
            "name": prefix + "-" + label,
            "valid_from": str(day + timedelta(days=start)),
            "valid_to": str(day + timedelta(days=end)),
            "participants": participants,
        }
        path = BASE + "/documents"
        if group is not None:
            body.pop("participants")
            path = BASE + f"/groups/{group}/documents"
        document = await api.request("admin", "POST", path, expected=201,
            data={"metadata": json.dumps(body)},
            files=[("files", ("matching.pdf", pdf(), "application/pdf"))])
        if group is None:
            roots.append(document)
        return document

    async def remove(document):
        impact = await api.request("admin", "GET", BASE + f"/documents/{document['id']}/monetization-usages")
        await api.request("admin", "DELETE", BASE + f"/documents/{document['id']}", expected=204,
            headers={"If-Match": impact["fingerprint"]})
        deleted.add(document["id"])

    async def candidates(context, role="admin"):
        return await api.request(role, "POST", BASE + "/monetization-candidates", json={"context": context})

    def program_body(label, context, document_ids):
        # source_type alone does not mean that the platform participates.
        expenses = [{"participant_type": "leasing", "base_type": "none", "calc_type": "amount", "value": "100"}]
        if context.get("platform_ml"):
            expenses.append({"participant_type": "platform", "base_type": "none", "calc_type": "amount", "value": "10"})
        return {
            "status": "inactive", "name": prefix + "-program-" + label,
            "leasing_company_id": context["leasing_company_id"],
            "dealer_company_id": context.get("dealer_company_id"),
            "distributor_company_id": context.get("distributor_company_id"),
            "brand": catalog["brand"] if context.get("mark_id") else None,
            "model": catalog["model"] if context.get("model_id") else None,
            "period_start": str(day),
            "sources": [{"source_type": "platform", "expenses": expenses, "incomes": []}],
            "reference_document_ids": document_ids,
        }

    async def link_ids(program_id):
        response = await api.request("admin", "GET", PROGRAMS + f"/{program_id}/reference-documents")
        return {document["id"] for document in response["items"]}

    async def replace(program_id, ids, expected=200, role="admin"):
        return await api.request(role, "PATCH", PROGRAMS + f"/{program_id}/reference-documents",
            expected=expected, json={"document_ids": ids})

    try:
        dense = await upload("all-criteria", {
            "leasing_company_ids": [lc], "dealer_company_ids": [dealer],
            "distributor_company_ids": [distributor], "mark_id": mark,
            "model_id": model, "platform_ml": True,
        })
        cases = [
            ("leasing-only", {"leasing_company_id": lc}),
            ("dealer-only", {"leasing_company_id": lc2, "dealer_company_id": dealer}),
            ("distributor-only", {"leasing_company_id": lc2, "distributor_company_id": distributor}),
            ("mark-only", {"leasing_company_id": lc2, "mark_id": mark}),
            # A valid model necessarily includes its matching mark.
            ("mark-and-model", {"leasing_company_id": lc2, "mark_id": mark, "model_id": model}),
            ("platform-only", {"leasing_company_id": lc2, "platform_ml": True}),
        ]
        for label, context in cases:
            result = await candidates(context)
            check(label + " offers document despite all other missing or different criteria",
                dense["id"] in {item["id"] for item in result["items"]})
            check(label + " offers its group",
                dense["group_id"] in {item["group_id"] for item in result["groups"]})
            body = program_body(label, context, [dense["id"]])
            program = await api.request("admin", "POST", PROGRAMS, expected=201, json=body)
            check(label + " is accepted during program creation", await link_ids(program["id"]) == {dense["id"]})
            saved_candidates = await api.request("admin", "POST", BASE + "/monetization-candidates",
                json={"program_id": program["id"]})
            check(label + " saved-program candidates use the same rule",
                dense["id"] in {item["id"] for item in saved_candidates["items"]})
            await replace(program["id"], [])
            await replace(program["id"], [dense["id"]])
            check(label + " is accepted when adding a link by PATCH", await link_ids(program["id"]) == {dense["id"]})

        # These payloads persist empty lists, null catalog fields and false platform.
        sparse = await upload("nulls-and-false", {"leasing_company_ids": [lc]})
        dealer_doc = await upload("dealer-with-empty-lc", {"dealer_company_ids": [dealer]})
        mark_doc = await upload("mark-with-empty-companies", {"mark_id": mark})
        platform_doc = await upload("platform-with-empty-companies", {"platform_ml": True})
        ours = {document["id"] for document in roots}
        no_hits = {"leasing_company_id": lc2, "dealer_company_id": None,
            "distributor_company_id": None, "mark_id": None, "model_id": None, "platform_ml": False}
        result = await candidates(no_hits)
        check("nulls, empty lists and false do not match when there are no positive hits",
            not ({item["id"] for item in result["items"]} & ours))
        check("no positive hits excludes groups too",
            not ({item["group_id"] for item in result["groups"]} & {item["group_id"] for item in roots}))
        for document, context, label in [
            (dealer_doc, {"leasing_company_id": lc2, "dealer_company_id": dealer}, "dealer without document LC"),
            (mark_doc, {"leasing_company_id": lc2, "mark_id": mark}, "mark without document companies"),
            (platform_doc, {"leasing_company_id": lc2, "platform_ml": True}, "platform without document companies"),
        ]:
            result = await candidates(context)
            check(label + " can independently match", document["id"] in {item["id"] for item in result["items"]})
        rejected = program_body("no-hits", no_hits, [sparse["id"]])
        await api.request("admin", "POST", PROGRAMS, expected=409, json=rejected)
        programs = await api.request("admin", "GET", PROGRAMS, params={"page_size": 100})
        check("rejected create leaves no partial program", not any(item["name"] == rejected["name"] for item in programs["items"]))
        empty_program = await api.request("admin", "POST", PROGRAMS, expected=201,
            json=program_body("empty", no_hits, []))
        await replace(empty_program["id"], [sparse["id"]], expected=409)
        check("rejected PATCH leaves links unchanged", await link_ids(empty_program["id"]) == set())

        eligible_context = {"leasing_company_id": lc}
        expired = await upload("expired", {"leasing_company_ids": [lc]}, start=-10, end=-1)
        stopped = await upload("deactivated", {"leasing_company_ids": [lc]})
        await api.request("admin", "PATCH", BASE + f"/documents/{stopped['id']}/activation", json={"active": False})
        removed = await upload("deleted", {"leasing_company_ids": [lc]})
        await remove(removed)
        pending = await upload("pending", {"leasing_company_ids": [lc]}, start=1)
        expiring = await upload("expiring", {"leasing_company_ids": [lc]}, end=1)
        result = await candidates(eligible_context)
        found = {item["id"] for item in result["items"]}
        check("status guards exclude expired and deactivated; deletion excludes deleted",
            not ({expired["id"], stopped["id"], removed["id"]} & found))
        check("active, expiring and pending remain eligible", {sparse["id"], pending["id"], expiring["id"]} <= found)
        check("inactive groups remain available for creating children; deleted group does not",
            {expired["group_id"], stopped["group_id"]} <= {item["group_id"] for item in result["groups"]}
            and removed["group_id"] not in {item["group_id"] for item in result["groups"]})
        child = await upload("new-child-in-inactive-group", {}, group=stopped["group_id"])
        result = await candidates(eligible_context)
        check("active child in deactivated main group is eligible by one match",
            child["id"] in {item["id"] for item in result["items"]})
        good = await api.request("admin", "POST", PROGRAMS, expected=201,
            json=program_body("status-guard", eligible_context, [pending["id"], expiring["id"], child["id"]]))
        good_ids = {pending["id"], expiring["id"], child["id"]}
        for document in (expired, stopped, removed):
            await replace(good["id"], sorted(good_ids | {document["id"]}), expected=409)
            check("ineligible link rejected atomically " + document["contract_number"], await link_ids(good["id"]) == good_ids)
            await api.request("admin", "POST", PROGRAMS, expected=409,
                json=program_body("invalid-" + document["id"], eligible_context, [document["id"]]))

        result = await candidates({"leasing_company_id": lc2, "dealer_company_id": dealer}, "dealer")
        check("authorized dealer sees dealer-only match", dense["id"] in {item["id"] for item in result["items"]})
        hidden = await candidates({"leasing_company_id": lc2, "dealer_company_id": dealer}, "outsider")
        check("context match never bypasses document ACL", dense["id"] not in {item["id"] for item in hidden["items"]}
            and dense["group_id"] not in {item["group_id"] for item in hidden["groups"]})
        await api.request("outsider", "GET", BASE + f"/documents/{dense['id']}", expected=404)
        await replace(good["id"], [], expected=403, role="dealer")
        for role, status in (("guest", 401), ("client", 403)):
            await api.request(role, "POST", BASE + "/monetization-candidates", expected=status, json={"context": eligible_context})
        for invalid in (
            {"leasing_company_id": str(uuid4()), "platform_ml": True},
            {"leasing_company_id": lc, "model_id": model},
            {"leasing_company_id": lc, "mark_id": str(uuid4()), "model_id": model},
        ):
            await api.request("admin", "POST", BASE + "/monetization-candidates", expected=409, json={"context": invalid})
        progress("matching_regression_passed", checks=checks, prefix=prefix)
    finally:
        failures = []
        for document in roots:
            if document["id"] not in deleted:
                try:
                    await remove(document)
                except Exception as exc:
                    failures.append(str(exc))
        progress("matching_cleanup", roots=len(roots), failures=failures)
        require(not failures, "Matching fixture document cleanup failed")


if __name__ == "__main__":
    asyncio.run(main())
