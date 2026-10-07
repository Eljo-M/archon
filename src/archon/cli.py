import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from archon.agents.orchestrator import Orchestrator
from archon.config import Settings
from archon.db.store import RunStore
from archon.domain import Issue, RepositorySpec, RunStatus
from archon.sandbox.trusted_fixture import TrustedFixtureRunner

ROOT = Path(__file__).resolve().parents[2]


class FixtureModel:
    """Deterministic responses for an explicitly labelled smoke test, not an inference model."""

    def __init__(self, patch: str):
        self.patch = patch

    async def complete(self, role, payload):
        if role == "Architect":
            return {"files": ["arithmetic.py"], "summary": "Locate add() in arithmetic.py"}
        if role == "Coder":
            return {"patch": self.patch, "summary": "Replace subtraction with addition"}
        return {"approved": True, "summary": "Source-only fix preserves the fixture tests"}


async def demo(database: Path):
    database.parent.mkdir(parents=True, exist_ok=True)
    store = RunStore(str(database))
    try:
        issue = Issue("fixture-addition", "add(2, 3) returns -1 instead of 5",
                      RepositorySpec("https://github.com/example/fixture", "0" * 40, "trusted-fixture",
                                     ("python", "-m", "unittest", "discover", "-s", "tests")), 2)
        import uuid
        run_id, _ = await store.create(issue, f"demo-{uuid.uuid4()}")
        engine = Orchestrator(store, FixtureModel((ROOT / "examples/fix.patch").read_text()), TrustedFixtureRunner())
        status = await engine.run(run_id, issue, ROOT / "examples/buggy_repo")
        print("Trusted fixture smoke test; model responses are scripted.")
        for event in await store.events(run_id):
            print(f"{event.sequence:02d} {event.stage}: {event.summary}")
        print(f"Run {run_id}: {status}; persisted to {database}")
        return 0 if status == RunStatus.SUCCEEDED else 1
    finally:
        store.close()


async def submit(issue_file: Path, target: str):
    import grpc
    from google.protobuf.json_format import ParseDict

    from archon.generated import archon_pb2 as pb
    from archon.generated import archon_pb2_grpc as rpc

    if not target.startswith(("localhost:", "127.0.0.1:")):
        raise ValueError("CLI plaintext development client requires loopback target")
    token = os.getenv("ARCHON_API_TOKEN", "")
    if not token:
        raise ValueError("ARCHON_API_TOKEN is required")
    request = ParseDict(json.loads(issue_file.read_text()), pb.IssueRequest())
    async with grpc.aio.insecure_channel(target) as channel:
        stub = rpc.AgentOrchestratorServiceStub(channel)
        async for event in stub.DispatchIssue(request, metadata=(("authorization", f"Bearer {token}"),)):
            print(json.dumps({"run_id": event.run_id, "sequence": event.sequence, "stage": event.stage,
                              "summary": event.summary, "status": event.status}))


def main():
    parser = argparse.ArgumentParser(description="Archon development commands")
    sub = parser.add_subparsers(dest="command", required=True)
    smoke = sub.add_parser("demo", help="Run the supplied trusted fixture with scripted model responses")
    smoke.add_argument("--database", type=Path, default=Path(".archon/demo.sqlite3"))
    server = sub.add_parser("serve", help="Start the single-process development gRPC gateway")
    server.add_argument("--database", type=Path, default=Path(".archon/runs.sqlite3"))
    client = sub.add_parser("submit", help="Submit a JSON issue request to a loopback gateway")
    client.add_argument("issue_file", type=Path)
    client.add_argument("--target", default="127.0.0.1:50051")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.command == "demo":
        raise SystemExit(asyncio.run(demo(args.database)))
    if args.command == "serve":
        from archon.gateway.server import serve
        asyncio.run(serve(Settings.from_env(), args.database))
    else:
        asyncio.run(submit(args.issue_file, args.target))


if __name__ == "__main__":
    main()
