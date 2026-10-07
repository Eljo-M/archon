import shlex
from pathlib import Path, PurePosixPath

PROTECTED = {".git", ".github", "tests", "test", ".archon", ".archon-control"}


def validate_patch(patch: str, workspace: Path) -> list[str]:
    """Restrict the initial patch format to textual changes to existing Python source."""
    if not patch or len(patch.encode()) > 64_000 or "\0" in patch:
        raise ValueError("patch must be nonempty text under 64 KB")
    headers = []
    metadata_paths = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            fields = shlex.split(line)
            if len(fields) != 4 or not fields[2].startswith("a/") or not fields[3].startswith("b/"):
                raise ValueError("unsupported git diff header")
            metadata_paths.append((fields[2][2:], fields[3][2:]))
        if line.startswith(("old mode ", "new mode ", "new file mode ", "deleted file mode ",
                            "rename from ", "rename to ", "copy from ", "copy to ",
                            "GIT binary patch", "Binary files ")):
            raise ValueError("mode changes, file creation/deletion, renames and binary patches are not supported")
        if line.startswith(("--- ", "+++ ")):
            name = line[4:]
            prefix = "a/" if line.startswith("--- ") else "b/"
            if not name.startswith(prefix):
                raise ValueError("patch headers must use standard a/ and b/ paths")
            name = name[2:]
            path = PurePosixPath(name)
            if (path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
                    or any(part in PROTECTED for part in path.parts) or path.suffix != ".py"
                    or path.name.startswith("test_") or path.name.endswith("_test.py")):
                raise ValueError("patch targets a protected or unsupported path")
            candidate = workspace.joinpath(*path.parts)
            if (not candidate.is_file() or candidate.is_symlink()
                    or workspace.resolve() not in candidate.resolve().parents):
                raise ValueError("patch must target an existing regular file inside the workspace")
            headers.append((prefix, name))
    if not headers or len(headers) % 2:
        raise ValueError("patch requires paired old/new headers")
    for old, new in zip(headers[::2], headers[1::2], strict=True):
        if old[0] != "a/" or new[0] != "b/" or old[1] != new[1]:
            raise ValueError("patch old/new paths must match")
    if metadata_paths != [(old[1], new[1]) for old, new in zip(headers[::2], headers[1::2], strict=True)]:
        raise ValueError("git diff metadata must match the old/new file paths")
    return list(dict.fromkeys(name for _, name in headers))
