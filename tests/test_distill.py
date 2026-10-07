import json

from archon.agents.orchestrator import Orchestrator
from archon.cli import FixtureModel
from archon.db.store import RunStore
from archon.domain import Event, RunStatus
from archon.sandbox.trusted_fixture import TrustedFixtureRunner
from archon.training.distill import export_verified


async def test_distillation_excludes_scripted_fixture(tmp_path, issue, workspace, patch):
    database = tmp_path / "runs.sqlite3"
    store = RunStore(str(database))
    try:
        run_id, _ = await store.create(issue, "fixture")
        await Orchestrator(store, FixtureModel(patch), TrustedFixtureRunner()).run(run_id, issue, workspace)
    finally:
        store.close()
    output = tmp_path / "dataset.jsonl"
    assert export_verified(database, output) == 0
    assert output.read_text() == ""


async def test_distillation_requires_matching_verified_execution(tmp_path, issue, patch):
    database = tmp_path / "runs.sqlite3"
    store = RunStore(str(database))
    try:
        run_id, _ = await store.create(issue, "verified")
        await store.append(Event(run_id, 0, "BASELINE_RESULT", "sandbox", "Failed",
                                 evidence={"status": "TEST_FAILED"}))
        await store.append(Event(run_id, 0, "TESTED", "sandbox", "Passed",
                                 evidence={"status": "PASSED", "execution_id": "verified-1", "image_id": "sha256:example"}))
        await store.append(Event(run_id, 0, "SUCCEEDED", "orchestrator", "Done", diff=patch,
                                 status=RunStatus.SUCCEEDED, evidence={"execution_id": "verified-1"}))
    finally:
        store.close()
    output = tmp_path / "dataset.jsonl"
    assert export_verified(database, output) == 1
    row = json.loads(output.read_text())
    assert row["messages"][1]["content"] == patch
    assert "thought_trace" not in row
