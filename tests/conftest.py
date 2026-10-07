from pathlib import Path

import pytest

from archon.db.store import RunStore
from archon.domain import Issue, RepositorySpec

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace():
    return ROOT / "examples/buggy_repo"


@pytest.fixture
def patch():
    return (ROOT / "examples/fix.patch").read_text()


@pytest.fixture
def issue():
    return Issue("addition", "add(2, 3) returns -1 rather than 5",
                 RepositorySpec("https://github.com/example/fixture", "0" * 40, "archon-sandbox:dev",
                                ("python", "-m", "unittest", "discover", "-s", "tests")), 2)


@pytest.fixture
def store():
    value = RunStore()
    yield value
    value.close()
