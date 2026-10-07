import asyncio
from dataclasses import replace

from archon.agents.orchestrator import Orchestrator
from archon.cli import FixtureModel
from archon.domain import ExecutionResult, ExecutionStatus, RunStatus
from archon.sandbox.trusted_fixture import TrustedFixtureRunner


async def test_real_fixture_repair_and_evidence(store, issue, workspace, patch):
    run_id, _ = await store.create(issue, "repair")
    status = await Orchestrator(store, FixtureModel(patch), TrustedFixtureRunner()).run(run_id, issue, workspace)
    events = await store.events(run_id)
    assert status == RunStatus.SUCCEEDED
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    baseline = next(event for event in events if event.stage == "BASELINE_RESULT")
    tested = next(event for event in events if event.stage == "TESTED")
    assert baseline.evidence["status"] == "TEST_FAILED"
    assert tested.evidence["status"] == "PASSED"
    assert events[-1].diff == patch
    assert "return left - right" in (workspace / "arithmetic.py").read_text()


async def test_retry_receives_test_feedback(store, issue, workspace, patch):
    class RetryModel(FixtureModel):
        attempts = 0

        async def complete(self, role, payload):
            if role == "Coder":
                self.attempts += 1
                if self.attempts == 1:
                    return {"patch": patch.replace("return left + right", "return left * right")}
                assert payload["feedback"]["execution"]["status"] == "TEST_FAILED"
                assert "previous_patch" in payload["feedback"]
            return await super().complete(role, payload)

    run_id, _ = await store.create(issue, "retry")
    model = RetryModel(patch)
    assert await Orchestrator(store, model, TrustedFixtureRunner()).run(run_id, issue, workspace) == RunStatus.SUCCEEDED
    assert model.attempts == 2


async def test_review_rejection_exhausts_budget(store, issue, workspace, patch):
    class RejectingModel(FixtureModel):
        async def complete(self, role, payload):
            if role == "Reviewer":
                return {"approved": "true", "summary": "Wrong JSON type"}
            return await super().complete(role, payload)

    run_id, _ = await store.create(issue, "review")
    assert await Orchestrator(store, RejectingModel(patch), TrustedFixtureRunner()).run(run_id, issue, workspace) == RunStatus.FAILED
    assert not any(event.stage == "TESTED" for event in await store.events(run_id))


async def test_baseline_pass_does_not_call_model(store, issue, workspace):
    class PassingSandbox:
        async def execute(self, workspace, repository, patch, execution_id):
            return ExecutionResult(execution_id, ExecutionStatus.PASSED, 0)

    class NoModel:
        async def complete(self, role, payload):
            raise AssertionError("No repair needed for passing baseline")

    run_id, _ = await store.create(issue, "already-pass")
    assert await Orchestrator(store, NoModel(), PassingSandbox()).run(run_id, issue, workspace) == RunStatus.FAILED
    assert (await store.events(run_id))[-1].summary == "Issue did not reproduce"


async def test_invalid_patch_never_reaches_test_executor(store, issue, workspace, patch):
    model = FixtureModel(patch.replace("arithmetic.py", "tests/test_arithmetic.py"))
    run_id, _ = await store.create(issue, "invalid")
    await Orchestrator(store, model, TrustedFixtureRunner()).run(run_id, issue, workspace)
    events = await store.events(run_id)
    assert len([event for event in events if event.stage == "PATCH_REJECTED"]) == 2
    assert events[-1].status == RunStatus.FAILED


async def test_cancellation_records_terminal_state(store, issue, workspace, patch):
    started = asyncio.Event()
    cleaned = asyncio.Event()

    class BlockingSandbox:
        async def execute(self, workspace, repository, patch, execution_id):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    run_id, _ = await store.create(issue, "cancel")
    task = asyncio.create_task(Orchestrator(store, FixtureModel(patch), BlockingSandbox()).run(run_id, issue, workspace))
    await started.wait()
    task.cancel()
    assert await task == RunStatus.CANCELLED
    assert cleaned.is_set()
    assert (await store.events(run_id))[-1].completed


async def test_execution_infrastructure_failure_stops_repairs(store, issue, workspace, patch):
    class FailingSandbox:
        calls = 0

        async def execute(self, workspace, repository, patch, execution_id):
            self.calls += 1
            return ExecutionResult(execution_id, ExecutionStatus.TEST_FAILED if self.calls == 1 else ExecutionStatus.TIMEOUT)

    runner = FailingSandbox()
    run_id, _ = await store.create(issue, "timeout")
    await Orchestrator(store, FixtureModel(patch), runner).run(run_id, replace(issue, max_repair_iterations=10), workspace)
    assert runner.calls == 2
    assert (await store.events(run_id))[-1].evidence["execution_status"] == "TIMEOUT"
