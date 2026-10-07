import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from archon.domain import RepositorySpec
from archon.sandbox.docker_runner import git_environment


async def git(*args: str, timeout: int = 120):
    process = await asyncio.create_subprocess_exec("git", "-c", "protocol.file.allow=never",
                                                   "-c", "protocol.ext.allow=never", "-c", "core.hooksPath=",
                                                   *args, env=git_environment(),
                                                   stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except (TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError("Git checkout failed; check repository access and immutable revision")


@asynccontextmanager
async def checkout(repository: RepositorySpec):
    with tempfile.TemporaryDirectory(prefix="archon-checkout-") as directory:
        root = Path(directory) / "source"
        await git("clone", "--no-checkout", "--no-tags", "--filter=blob:none", repository.url, str(root))
        await git("-C", str(root), "fetch", "--depth=1", "origin", repository.commit)
        await git("-C", str(root), "checkout", "--detach", repository.commit)
        yield root
