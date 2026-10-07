"""For the shipped trusted fixture only. Never selected by the gateway or for user repositories."""

import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

from archon.domain import ExecutionResult, ExecutionStatus, RepositorySpec
from archon.sandbox.docker_runner import git_environment
from archon.sandbox.patches import validate_patch


class TrustedFixtureRunner:
    async def execute(self, workspace: Path, repository: RepositorySpec,
                      patch: str, execution_id: str) -> ExecutionResult:
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="archon-fixture-") as directory:
            target = Path(directory) / "repo"
            shutil.copytree(workspace, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            if patch:
                try:
                    validate_patch(patch, target)
                except ValueError as error:
                    return ExecutionResult(execution_id, ExecutionStatus.INVALID_PATCH, stderr=str(error))
                process = await asyncio.create_subprocess_exec("git", "apply", "--whitespace=error", "-",
                                                               cwd=target, env=git_environment(), stdin=asyncio.subprocess.PIPE,
                                                               stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await process.communicate(patch.encode())
                if process.returncode:
                    return ExecutionResult(execution_id, ExecutionStatus.INVALID_PATCH,
                                           process.returncode, stderr=stderr.decode(errors="replace"))
            # Ignore caller-supplied commands: this runner executes only the shipped fixture test file.
            process = await asyncio.create_subprocess_exec(sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                                           cwd=target, stdout=asyncio.subprocess.PIPE,
                                                           stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), repository.timeout_seconds)
            except (TimeoutError, asyncio.CancelledError):
                process.kill()
                await process.wait()
                raise
            status = ExecutionStatus.PASSED if process.returncode == 0 else ExecutionStatus.TEST_FAILED
            return ExecutionResult(execution_id, status, process.returncode,
                                   stdout.decode(errors="replace"), stderr.decode(errors="replace"),
                                   int((time.monotonic() - started) * 1000), image_id="trusted-fixture-host")
