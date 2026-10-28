"""End-to-end API flow with fake agents: upload -> questions -> build -> approve / reject."""
from conftest import parsed_runbook, upload


def test_full_flow_to_approval(client, client_as, fakes):
    record = upload(client)
    assert record["status"] == "awaiting_approval"
    assert record["parsed"]["title"] == "Restart nginx"
    assert record["submitted_by_name"] == "Alice"
    assert len(record["scripts"]) == 1
    assert record["test_runs"][0]["passed"] is True
    assert record["review"]["script_version"] == 1

    approved = client_as("bob").post(f"/runbooks/{record['id']}/approve", json={"comment": "ok"}).json()
    assert approved["status"] == "approved"
    assert approved["approved_version"] == 1
    assert approved["approvals"][0]["reviewer"] == "Bob"
    assert any("Bob approved script v1" in e["message"] for e in approved["events"])


def test_questions_block_build_until_answered(client, fakes):
    fakes.parsed = parsed_runbook(ambiguous_step=1)
    record = upload(client)
    assert record["status"] == "needs_answers"
    assert client.post(f"/runbooks/{record['id']}/build").status_code == 409

    answered = client.post(f"/runbooks/{record['id']}/answers?wait=true", json={"answers": {"1": "app-web-01"}}).json()
    assert answered["status"] == "awaiting_approval"
    assert answered["parsed"]["steps"][0]["answer"] == "app-web-01"


def test_high_risk_needs_two_different_approvers(client, client_as, fakes):
    fakes.parsed = parsed_runbook(risk="high")
    rid = upload(client)["id"]
    bob, carol = client_as("bob"), client_as("carol")

    first = bob.post(f"/runbooks/{rid}/approve").json()
    assert first["status"] == "awaiting_approval"
    assert bob.post(f"/runbooks/{rid}/approve").status_code == 409  # same person twice
    second = carol.post(f"/runbooks/{rid}/approve").json()
    assert second["status"] == "approved"


def test_reject_sends_feedback_to_author(client, client_as, fakes):
    rid = upload(client)["id"]
    after = client_as("bob").post(f"/runbooks/{rid}/reject?wait=true", json={"comment": "Use reload, not restart"}).json()
    assert fakes.author_calls[-1] == "Reviewer rejected the script: Use reload, not restart"
    assert len(after["scripts"]) == 2
    assert after["status"] == "awaiting_approval"
    assert after["approvals"][0]["decision"] == "rejected"


def test_approve_requires_right_state(client, client_as, fakes):
    fakes.parsed = parsed_runbook(ambiguous_step=2)
    rid = upload(client)["id"]
    assert client_as("bob").post(f"/runbooks/{rid}/approve").status_code == 409


def test_queued_jobs_wait_for_worker(client, fakes):
    from app.worker import Worker

    record = upload(client, wait=False)
    assert record["status"] == "queued"
    assert client.post(f"/runbooks/{record['id']}/build").status_code == 409  # busy

    worker = Worker()
    assert worker.run_one() is True
    assert worker.run_one() is False  # queue empty
    assert client.get(f"/runbooks/{record['id']}").json()["status"] == "awaiting_approval"


def test_list_delete_and_404(client, client_as, fakes):
    rid = upload(client)["id"]
    rows = client.get("/runbooks").json()
    assert rows[0]["id"] == rid and rows[0]["script_versions"] == 1
    assert client_as("bob").delete(f"/runbooks/{rid}").status_code == 403  # not the uploader, not admin
    assert client.delete(f"/runbooks/{rid}").status_code == 200
    assert client.get(f"/runbooks/{rid}").status_code == 404


def test_unsupported_upload(client):
    response = client.post("/runbooks", files={"file": ("tool.exe", b"MZ")})
    assert response.status_code == 400
