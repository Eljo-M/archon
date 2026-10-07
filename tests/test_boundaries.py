from dataclasses import replace

import pytest

from archon.codegraph.index import CodeIndex, safe_source_path
from archon.domain import Event, RunStatus
from archon.sandbox.docker_runner import source_archive
from archon.sandbox.patches import validate_patch


@pytest.mark.parametrize("url", ["file:///tmp/repo", "https://evil.example/repo", "https://user:secret@github.com/a/b",
                                "http://github.com/a/b", "https://github.com:8443/a/b"])
def test_repository_validation_rejects_unsafe_origins(issue, url):
    with pytest.raises(ValueError):
        replace(issue.repository, url=url).validate(allowed_hosts={"github.com"}, allowed_image="archon-sandbox:dev")


@pytest.mark.parametrize("commit", ["main", "deadbeef", "-option", "z" * 40])
def test_repository_revision_is_immutable(issue, commit):
    with pytest.raises(ValueError):
        replace(issue.repository, commit=commit).validate(allowed_hosts={"github.com"}, allowed_image="archon-sandbox:dev")


def test_index_exposes_relevant_function_with_lines(workspace):
    index = CodeIndex(workspace)
    index.build()
    symbol = index.relevant("add arithmetic")[0]
    assert symbol["name"] == "add"
    assert symbol["path"] == "arithmetic.py"
    assert symbol["start_line"] == 1
    assert symbol["end_line"] == 2


@pytest.mark.parametrize("path", ["../outside.py", "/outside.py", "C:/outside.py", "tests\\test_arithmetic.py"])
def test_source_paths_are_contained(workspace, path):
    with pytest.raises(ValueError):
        safe_source_path(workspace, path)


@pytest.mark.parametrize("target", ["../outside.py", "tests/test_arithmetic.py", ".github/workflow.py", "C:/outside.py"])
def test_patch_rejects_protected_paths(workspace, patch, target):
    with pytest.raises(ValueError):
        validate_patch(patch.replace("arithmetic.py", target), workspace)


def test_patch_rejects_mode_change(workspace, patch):
    with pytest.raises(ValueError):
        validate_patch("new mode 120000\n" + patch, workspace)


def test_patch_rejects_inconsistent_git_metadata(workspace, patch):
    malicious = patch.replace("diff --git a/arithmetic.py b/arithmetic.py", "diff --git a/.gitattributes b/.gitattributes")
    with pytest.raises(ValueError):
        validate_patch(malicious, workspace)


def test_archive_omits_git_metadata_and_normalizes_ownership(workspace):
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(source_archive(workspace))) as archive:
        members = archive.getmembers()
        assert any(member.name == "arithmetic.py" for member in members)
        assert all(member.uid == 65534 and member.isfile() for member in members)


async def test_idempotency_conflict_and_terminal_immutability(store, issue):
    run_id, created = await store.create(issue, "same")
    assert created
    assert await store.create(issue, "same") == (run_id, False)
    with pytest.raises(ValueError):
        await store.create(replace(issue, description="different issue"), "same")
    await store.append(Event(run_id, 0, "FAILED", "test", "Done", status=RunStatus.FAILED))
    with pytest.raises(ValueError):
        await store.append(Event(run_id, 0, "TESTED", "test", "Late result"))
    assert not await store.cancel(run_id)


async def test_store_restart_records_interruption(tmp_path, issue):
    from archon.db.store import RunStore
    database = str(tmp_path / "runs.sqlite3")
    initial = RunStore(database)
    run_id, _ = await initial.create(issue, "restart")
    initial.close()
    resumed = RunStore(database)
    try:
        assert await resumed.recover_interrupted() == 1
        assert (await resumed.get(run_id))["status"] == RunStatus.FAILED
        assert (await resumed.events(run_id, after=1))[0].evidence["category"] == "INFRA_ERROR"
    finally:
        resumed.close()
