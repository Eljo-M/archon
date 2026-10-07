from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


class ExecutionStatus(StrEnum):
    PASSED = "PASSED"
    TEST_FAILED = "TEST_FAILED"
    INVALID_PATCH = "INVALID_PATCH"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    INFRA_ERROR = "INFRA_ERROR"


class LeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class RepositorySpec:
    url: str
    commit: str
    image: str
    test_argv: tuple[str, ...]
    timeout_seconds: int = 120

    def validate(self, *, allowed_hosts: set[str], allowed_image: str) -> None:
        parsed = urlsplit(self.url)
        if (parsed.scheme != "https" or parsed.hostname not in allowed_hosts
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.query or parsed.fragment):
            raise ValueError("repository must be an allowlisted HTTPS URL without credentials")
        if not re.fullmatch(r"[0-9a-f]{40}", self.commit):
            raise ValueError("commit must be a full lowercase 40-character Git SHA")
        if self.image != allowed_image:
            raise ValueError("sandbox image must match the worker's configured image")
        if not self.test_argv or any(not arg or "\0" in arg for arg in self.test_argv):
            raise ValueError("test_argv must contain nonempty arguments without NUL")
        if len(self.test_argv) > 64 or sum(map(len, self.test_argv)) > 8192:
            raise ValueError("test command exceeds size limits")
        if not 1 <= self.timeout_seconds <= 600:
            raise ValueError("timeout must be between 1 and 600 seconds")


@dataclass(frozen=True)
class Issue:
    issue_id: str
    description: str
    repository: RepositorySpec
    max_repair_iterations: int = 3

    def validate(self, **kwargs) -> None:
        if not self.issue_id or not self.description or len(self.description) > 32_000:
            raise ValueError("issue ID and bounded description are required")
        if not 1 <= self.max_repair_iterations <= 10:
            raise ValueError("repair budget must be between 1 and 10")
        self.repository.validate(**kwargs)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Issue:
        repo = dict(data["repository"])
        repo["test_argv"] = tuple(repo["test_argv"])
        return cls(data["issue_id"], data["description"], RepositorySpec(**repo),
                   data["max_repair_iterations"])

    def fingerprint(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


@dataclass
class ExecutionResult:
    execution_id: str
    status: ExecutionStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: int = 0
    output_truncated: bool = False
    image_id: str = ""

    @property
    def passed(self) -> bool:
        return self.status == ExecutionStatus.PASSED

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Event:
    run_id: str
    sequence: int
    stage: str
    agent: str
    summary: str
    attempt: int = 0
    diff: str = ""
    status: RunStatus = RunStatus.RUNNING
    evidence: dict = field(default_factory=dict)
    timestamp: str = ""

    @property
    def completed(self) -> bool:
        return self.status in TERMINAL

    def to_dict(self) -> dict:
        return asdict(self)


class Sandbox(Protocol):
    async def execute(self, workspace: Path, repository: RepositorySpec,
                      patch: str, execution_id: str) -> ExecutionResult: ...


class Model(Protocol):
    async def complete(self, role: str, payload: dict) -> dict: ...
