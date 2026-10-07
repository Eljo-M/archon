import asyncio
from pathlib import Path

from archon.codegraph.index import CodeIndex
from archon.db.store import RunStore
from archon.domain import Event, ExecutionStatus, Issue, Model, RunStatus, Sandbox
from archon.sandbox.patches import validate_patch


class Orchestrator:
    def __init__(self, store: RunStore, model: Model, sandbox: Sandbox):
        self.store, self.model, self.sandbox = store, model, sandbox

    async def run(self, run_id: str, issue: Issue, workspace: Path) -> RunStatus:
        async def emit(stage, agent, summary, *, attempt=0, diff="", status=RunStatus.RUNNING, evidence=None):
            return await self.store.append(Event(run_id, 0, stage, agent, str(summary)[:2000],
                                                attempt, diff, status, evidence or {}))

        async def check_cancelled():
            if (await self.store.get(run_id))["cancel_requested"]:
                raise asyncio.CancelledError

        try:
            await check_cancelled()
            await emit("BASELINE", "sandbox", "Reproduce failure on the original revision")
            baseline = await self.sandbox.execute(workspace, issue.repository, "", f"{run_id}:baseline")
            await emit("BASELINE_RESULT", "sandbox", baseline.status, evidence=baseline.to_dict())
            await check_cancelled()
            if baseline.status != ExecutionStatus.TEST_FAILED:
                message = "Issue did not reproduce" if baseline.passed else "Baseline execution could not be verified"
                await emit("FAILED", "orchestrator", message, status=RunStatus.FAILED,
                           evidence={"baseline_status": baseline.status})
                return RunStatus.FAILED

            index = CodeIndex(workspace)
            await asyncio.to_thread(index.build)
            symbols = index.relevant(issue.description)
            architecture = await self.model.complete("Architect", {"issue": issue.description, "symbols": symbols,
                                                                    "baseline": baseline.to_dict()})
            paths = architecture.get("files")
            if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
                raise ValueError("Architect response requires a list of file paths")
            sources = index.read_sources(paths)
            await emit("LOCATED", "Architect", architecture.get("summary", "Located source files"),
                       evidence={"files": list(sources), "symbols": symbols})
            feedback = {"execution": baseline.to_dict()}
            for attempt in range(1, issue.max_repair_iterations + 1):
                await check_cancelled()
                response = await self.model.complete("Coder", {"issue": issue.description,
                                                                "original_sources": sources, "feedback": feedback})
                patch = response.get("patch")
                try:
                    if not isinstance(patch, str):
                        raise ValueError("Coder response requires a patch string")
                    validate_patch(patch, workspace)
                except ValueError as error:
                    feedback = {"validation_error": str(error)}
                    await emit("PATCH_REJECTED", "Reviewer", str(error), attempt=attempt)
                    continue
                await emit("PATCHED", "Coder", response.get("summary", "Generated patch"),
                           attempt=attempt, diff=patch)
                review = await self.model.complete("Reviewer", {"issue": issue.description,
                                                                 "original_sources": sources, "patch": patch})
                approved = review.get("approved") is True
                await emit("REVIEWED", "Reviewer", review.get("summary", "Reviewed patch"),
                           attempt=attempt, evidence={"approved": approved})
                await check_cancelled()
                if not approved:
                    feedback = {"review": review, "previous_patch": patch}
                    continue
                result = await self.sandbox.execute(workspace, issue.repository, patch, f"{run_id}:{attempt}")
                await emit("TESTED", "sandbox", result.status, attempt=attempt, evidence=result.to_dict())
                await check_cancelled()
                if result.passed:
                    await emit("SUCCEEDED", "orchestrator", "Reviewed patch passed the configured test command",
                               attempt=attempt, diff=patch, status=RunStatus.SUCCEEDED,
                               evidence={"execution_id": result.execution_id})
                    return RunStatus.SUCCEEDED
                if result.status in {ExecutionStatus.INFRA_ERROR, ExecutionStatus.RESOURCE_LIMIT, ExecutionStatus.TIMEOUT}:
                    await emit("FAILED", "orchestrator", "Execution failed outside the test oracle",
                               attempt=attempt, status=RunStatus.FAILED,
                               evidence={"execution_status": result.status})
                    return RunStatus.FAILED
                feedback = {"execution": result.to_dict(), "previous_patch": patch}
            await emit("FAILED", "orchestrator", "Repair budget exhausted", status=RunStatus.FAILED)
            return RunStatus.FAILED
        except asyncio.CancelledError:
            await emit("CANCELLED", "orchestrator", "Run cancelled and executor cleanup requested",
                       status=RunStatus.CANCELLED)
            return RunStatus.CANCELLED
        except Exception as error:
            # Do not persist exceptions that may contain credentials, model endpoint headers or host paths.
            await emit("FAILED", "orchestrator", f"Run stopped: {type(error).__name__}",
                       status=RunStatus.FAILED, evidence={"category": "INFRA_ERROR"})
            return RunStatus.FAILED
