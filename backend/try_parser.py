"""Quick check: run the Parser agent on a runbook file and print the steps.

Usage:  python try_parser.py ../samples/restart-web-service.md
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from app.agents.parser import parse_runbook
from app.documents import extract_text

path = Path(sys.argv[1] if len(sys.argv) > 1 else "../samples/restart-web-service.md")
text = extract_text(path.name, path.read_bytes())
result = parse_runbook(text)

print(f"\n{result.get('title')}  |  OS: {result.get('target_os')}  |  risk: {result.get('risk_tier')}")
print(f"  {result.get('risk_reason')}\n")
for step in result["steps"]:
    flag = "  ?? " if step.get("ambiguous") else "     "
    print(f"{flag}{step['order']}. {step['action']}")
    if step.get("command"):
        print(f"        $ {step['command']}")
    if step.get("question"):
        print(f"        QUESTION: {step['question']}")

print("\nFull JSON:\n" + json.dumps(result, indent=2))
