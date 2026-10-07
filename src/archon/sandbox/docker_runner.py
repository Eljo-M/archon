import asyncio
import contextlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
from pathlib import Path

from docker.types import LogConfig

import docker
from archon.domain import ExecutionResult, ExecutionStatus, RepositorySpec
from archon.sandbox.patches import validate_patch

OUTPUT_LIMIT = 64_000


def git_environment() -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return environment


def source_archive(root: Path) -> bytes:
    """Reject links and bound the upload; copy regular source files only."""
    buffer = io.BytesIO()
    total = count = 0
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if any(part in {".git", "__pycache__", ".venv", "node_modules"} for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError("sandbox snapshot cannot contain symbolic links")
            if not path.is_file():
                continue
            count += 1
            total += path.stat().st_size
            if count > 10_000 or total > 32_000_000:
                raise ValueError("sandbox snapshot exceeds initial size limit")
            info = archive.gettarinfo(str(path), arcname=relative.as_posix())
            info.uid = info.gid = 65534
            info.uname = info.gname = "nobody"
            info.mode = 0o644
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return buffer.getvalue()


class DockerRunner:
    """Disposable test containers through Docker Engine API; no host mounts or daemon socket inside."""

    async def execute(self, workspace: Path, repository: RepositorySpec,
                      patch: str, execution_id: str) -> ExecutionResult:
        cancel = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(self._execute, workspace, repository, patch,
                                                    execution_id, cancel))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancel.set()
            await asyncio.shield(task)  # Wait for kill/removal before workspace lifetime ends.
            raise

    def _execute(self, workspace, repository, patch, execution_id, cancel):
        started = time.monotonic()
        container = stream = reader = client = None
        buffers = [bytearray(), bytearray()]
        truncated = False
        read_errors = []

        def collect():
            nonlocal truncated
            try:
                for pair in stream:
                    for position, chunk in enumerate(pair):
                        if chunk:
                            remaining = OUTPUT_LIMIT - len(buffers[position])
                            buffers[position].extend(chunk[:remaining])
                            truncated |= len(chunk) > remaining
            except Exception as error:
                read_errors.append(type(error).__name__)

        try:
            with tempfile.TemporaryDirectory(prefix="archon-snapshot-") as directory:
                snapshot = Path(directory) / "source"
                # Validate before copying, so a linked file cannot pull host data into the snapshot.
                source_archive(workspace)
                shutil.copytree(workspace, snapshot, ignore=shutil.ignore_patterns(
                    ".git", "__pycache__", ".venv", "node_modules"))
                if patch:
                    try:
                        validate_patch(patch, snapshot)
                        check = subprocess.run(["git", "apply", "--check", "--whitespace=error", "-"],
                                               input=patch.encode(), cwd=snapshot, env=git_environment(),
                                               capture_output=True, timeout=10)
                        if check.returncode:
                            raise ValueError(check.stderr.decode(errors="replace")[:2000])
                        subprocess.run(["git", "apply", "--whitespace=error", "-"], input=patch.encode(),
                                       cwd=snapshot, env=git_environment(), capture_output=True,
                                       check=True, timeout=10)
                    except (ValueError, subprocess.CalledProcessError) as error:
                        return ExecutionResult(execution_id, ExecutionStatus.INVALID_PATCH, stderr=str(error)[:2000])
                payload = source_archive(snapshot)
                client = docker.from_env(timeout=5)
                image = client.images.get(repository.image)
                container = client.containers.create(
                    image.id, command=list(repository.test_argv), working_dir="/workspace",
                    user="65534:65534", network_disabled=True, cap_drop=["ALL"],
                    security_opt=["no-new-privileges:true"], mem_limit="512m", memswap_limit="512m",
                    nano_cpus=1_000_000_000, pids_limit=128, init=True,
                    tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"},
                    environment={"PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
                    log_config=LogConfig(type="local", config={"max-size": "1m", "max-file": "1"}),
                    labels={"archon.execution_id": execution_id},
                )
                if not container.put_archive("/workspace", payload):
                    raise RuntimeError("Docker rejected source archive")
                if cancel.is_set():
                    return ExecutionResult(execution_id, ExecutionStatus.INFRA_ERROR, stderr="Cancelled before start")
                container.start()
                stream = container.attach(stream=True, logs=True, demux=True)
                reader = threading.Thread(target=collect, daemon=True)
                reader.start()
                deadline = time.monotonic() + repository.timeout_seconds
                status = None
                while True:
                    container.reload()
                    if not container.attrs["State"]["Running"]:
                        break
                    if cancel.is_set() or time.monotonic() >= deadline:
                        container.kill()
                        status = ExecutionStatus.TIMEOUT if not cancel.is_set() else ExecutionStatus.INFRA_ERROR
                        container.wait(timeout=5)
                        container.reload()
                        break
                    cancel.wait(0.1)
                reader.join(timeout=5)
                state = container.attrs["State"]
                if status is None:
                    status = (ExecutionStatus.RESOURCE_LIMIT if state.get("OOMKilled") else
                              ExecutionStatus.PASSED if state["ExitCode"] == 0 else ExecutionStatus.TEST_FAILED)
                if reader.is_alive() or read_errors:
                    status = ExecutionStatus.INFRA_ERROR
                return ExecutionResult(execution_id, status, state["ExitCode"],
                                       buffers[0].decode(errors="replace"), buffers[1].decode(errors="replace"),
                                       int((time.monotonic() - started) * 1000), truncated, image.id)
        except Exception as error:
            return ExecutionResult(execution_id, ExecutionStatus.INFRA_ERROR,
                                   stderr=f"Docker execution failed: {type(error).__name__}")
        finally:
            if stream is not None:
                with contextlib.suppress(Exception):
                    stream.close()
            if container is not None:
                with contextlib.suppress(Exception):
                    container.remove(force=True)
            if reader is not None:
                reader.join(timeout=2)
            if client is not None:
                client.close()
