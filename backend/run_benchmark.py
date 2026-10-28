"""Benchmark: run the sample runbooks through the full pipeline and report the results.

Each runbook is uploaded, its questions are answered from samples/engineer-answers.json, and the
agents write, test and review the script. Results show up in the web app's Impact dashboard.
Nothing is approved automatically; that stays a human decision.

Usage:  python run_benchmark.py                 (all samples)
        python run_benchmark.py clear-app-cache.md check-ssl-certificate.md
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from app.service_accounts import client_for

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
ANSWERS = json.loads((SAMPLES / "engineer-answers.json").read_text(encoding="utf-8"))

client = client_for("benchmark", ("submitter",), "Benchmark runner")
names = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(p.name for p in SAMPLES.glob("*.md"))

results = []
for name in names:
    path = SAMPLES / name
    started = time.monotonic()
    print(f"\n=== {name}")
    record = client.post("/runbooks?wait=true", files={"file": (name, path.read_bytes())}).json()
    rid = record["id"]
    questions = [s for s in record.get("parsed", {}).get("steps", []) if s.get("ambiguous")]
    if record["status"] == "needs_answers":
        notes = ANSWERS.get(name, "Use the safest read-only interpretation.")
        print(f"    {len(questions)} question(s), answering from engineer notes")
        record = client.post(f"/runbooks/{rid}/answers?wait=true", json={"answers": {s["order"]: notes for s in questions}}).json()

    review = record.get("review") or {}
    row = {
        "runbook": name,
        "id": rid,
        "status": record["status"],
        "risk": (record.get("parsed") or {}).get("risk_tier"),
        "steps": len((record.get("parsed") or {}).get("steps", [])),
        "questions": len(questions),
        "attempts": review.get("attempts") or len(record.get("test_runs", [])),
        "seconds": round(time.monotonic() - started),
        "recommendation": review.get("recommendation"),
    }
    results.append(row)
    for e in record.get("events", [])[-4:]:
        print(f"    [{e['agent']:8}] {e['message'][:140]}")
    print(f"    -> {row['status']} after {row['attempts']} attempt(s) in {row['seconds']}s")

print("\n" + "-" * 96)
print(f"{'runbook':34} {'risk':7} {'steps':>5} {'qs':>3} {'tries':>5} {'secs':>5}  status")
for r in results:
    print(f"{r['runbook']:34} {r['risk'] or '-':7} {r['steps']:>5} {r['questions']:>3} {r['attempts']:>5} {r['seconds']:>5}  {r['status']}")
passed = [r for r in results if r["status"] in ("awaiting_approval", "approved")]
print(f"\nConverted (tests passed, ready for approval): {len(passed)} of {len(results)}")
print(f"Passed on the first attempt: {sum(r['attempts'] == 1 for r in passed)} of {len(results)}")
