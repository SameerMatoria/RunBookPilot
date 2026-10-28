"""Quick check of the full flow through the API: upload -> Parser -> answers -> Author -> sandbox
test/fix -> Reviewer card -> approve.

Usage:  python try_pipeline.py [runbook file] [--show-script]
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from app.service_accounts import client_for

# Canned engineer answers for the sample runbook (keyed by keywords in the question).
SAMPLE_ANSWERS = {
    "log": "Delete *.gz and *.1 rotated log files older than 7 days under /var/log/nginx only.",
    "ok": "OK means nginx is active and the health check returns 200. Skip the ticket update; it is done by hand.",
    "server": "The script runs directly on the affected server; no SSH needed.",
}

client = client_for("smoke-test", ("submitter",), "Smoke test")
approver = client_for("smoke-approver", ("approver",), "Smoke test approver")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
path = Path(args[0] if args else "../samples/restart-web-service.md")

print(f"Uploading {path.name}")
record = client.post("/runbooks?wait=true", files={"file": (path.name, path.read_bytes())}).raise_for_status().json()
rid = record["id"]

questions = [s for s in record["parsed"]["steps"] if s.get("ambiguous")]
if questions:
    answers = {
        s["order"]: next((a for k, a in SAMPLE_ANSWERS.items() if k in s["question"].lower()), "Use the safest read-only check.")
        for s in questions
    }
    record = client.post(f"/runbooks/{rid}/answers?wait=true", json={"answers": answers}).raise_for_status().json()

if record["status"] == "awaiting_approval":
    record = approver.post(f"/runbooks/{rid}/approve", json={"comment": "Looks good"}).raise_for_status().json()

print("\nActivity log:")
for e in record["events"]:
    print(f"  [{e['agent']:9}] {e['message']}")

if record.get("review"):
    r = record["review"]
    print(f"\nReview card (v{r['script_version']}, {r['attempts']} attempt(s)): {r.get('headline')}")
    print(f"  recommendation={r.get('recommendation')} confidence={r.get('confidence')}: {r.get('confidence_reason')}")
    for risk in r.get("risks", []):
        print(f"  risk: {risk.get('risk')} -> {risk.get('mitigation')}")
    for item in r.get("untested", []):
        print(f"  untested: {item}")

print(f"\nFinal status: {record['status']}  (id {rid})")
if "--show-script" in sys.argv and record.get("scripts"):
    print("\n" + record["scripts"][-1]["script"])
