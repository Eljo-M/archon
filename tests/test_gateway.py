import asyncio
from contextlib import asynccontextmanager

import grpc
import pytest

from archon.agents.orchestrator import Orchestrator
from archon.cli import FixtureModel
from archon.config import Settings
from archon.domain import RunStatus
from archon.gateway.server import Gateway
from archon.generated import archon_pb2 as pb
from archon.generated import archon_pb2_grpc as rpc
from archon.sandbox.trusted_fixture import TrustedFixtureRunner


@pytest.fixture
async def gateway(store, workspace, patch):
    @asynccontextmanager
    async def local_checkout(repository):
        yield workspace

    value = Gateway(Settings(api_token="test-token"), store,
                    Orchestrator(store, FixtureModel(patch), TrustedFixtureRunner()), local_checkout)
    server = grpc.aio.server()
    rpc.add_AgentOrchestratorServiceServicer_to_server(value, server)
    rpc.add_ClusterCoordinatorServicer_to_server(value, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
        yield value, rpc.AgentOrchestratorServiceStub(channel), rpc.ClusterCoordinatorStub(channel)
    await value.close()
    await server.stop(0)


def request():
    return pb.IssueRequest(issue_id="addition", issue_description="add returns subtraction",
                           max_repair_iterations=2, idempotency_key="gateway-add",
                           repository=pb.RepositorySpec(url="https://github.com/example/fixture", commit_sha="0" * 40,
                                                        sandbox_image="archon-sandbox:dev",
                                                        test_argv=["python", "-m", "unittest", "discover", "-s", "tests"],
                                                        timeout_seconds=120))


AUTH = (("authorization", "Bearer test-token"),)


async def test_rpc_repair_and_replay(gateway):
    _, stub, _ = gateway
    submission = await stub.SubmitIssue(request(), metadata=AUTH)
    events = [event async for event in stub.WatchRun(pb.WatchRequest(run_id=submission.run_id), metadata=AUTH)]
    assert events[-1].success and events[-1].is_completed
    assert all(not event.thought_trace for event in events)
    retry = await stub.SubmitIssue(request(), metadata=AUTH)
    assert retry.run_id == submission.run_id and not retry.created
    replay = [event async for event in stub.WatchRun(pb.WatchRequest(run_id=submission.run_id, after_sequence=events[-2].sequence), metadata=AUTH)]
    assert len(replay) == 1 and replay[0].success


async def test_unauthorized_submission_rejected(gateway):
    _, stub, _ = gateway
    with pytest.raises(grpc.aio.AioRpcError) as failure:
        await stub.SubmitIssue(request())
    assert failure.value.code() == grpc.StatusCode.UNAUTHENTICATED


async def test_invalid_submission_rejected(gateway):
    _, stub, _ = gateway
    invalid = request()
    invalid.max_repair_iterations = 0
    with pytest.raises(grpc.aio.AioRpcError) as failure:
        await stub.SubmitIssue(invalid, metadata=AUTH)
    assert failure.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_watch_disconnect_preserves_background_job(gateway, store):
    value, stub, _ = gateway
    submission = await stub.SubmitIssue(request(), metadata=AUTH)
    watch = stub.WatchRun(pb.WatchRequest(run_id=submission.run_id), metadata=AUTH)
    await watch.read()
    watch.cancel()
    tasks = list(value.tasks.values())
    await asyncio.gather(*tasks)
    assert (await store.get(submission.run_id))["status"] == RunStatus.SUCCEEDED


async def test_cancellation_while_queued_has_terminal_event(gateway, store):
    value, stub, _ = gateway
    await value.semaphore.acquire()
    await value.semaphore.acquire()
    try:
        submission = await stub.SubmitIssue(request(), metadata=AUTH)
        result = await stub.CancelRun(pb.CancelRequest(run_id=submission.run_id), metadata=AUTH)
        assert result.accepted
        events = [event async for event in stub.WatchRun(pb.WatchRequest(run_id=submission.run_id), metadata=AUTH)]
        assert events[-1].status == "CANCELLED"
    finally:
        value.semaphore.release()
        value.semaphore.release()


async def test_coordinator_registration_and_heartbeat(gateway):
    _, _, coordinator = gateway
    unknown = await coordinator.SendHeartbeat(pb.HeartbeatRequest(node_id="unknown"), metadata=AUTH)
    assert not unknown.acknowledged
    registered = await coordinator.RegisterNode(pb.NodeInfo(node_id="worker", ip_address="127.0.0.1", port=50052,
                                                            cpu_cores=2), metadata=AUTH)
    assert registered.accepted
    alive = await coordinator.SendHeartbeat(pb.HeartbeatRequest(node_id="worker", gpu_utilization=0.5), metadata=AUTH)
    assert alive.acknowledged


async def test_shutdown_before_background_job_starts_persists_cancellation(gateway, store, issue):
    value, _, _ = gateway
    run_id, _ = await store.create(issue, "shutdown-before-start")
    value.tasks[run_id] = asyncio.create_task(value._run(run_id, issue))
    value.tasks[run_id].add_done_callback(lambda _: value.tasks.pop(run_id, None))
    await value.close()
    assert (await store.get(run_id))["status"] == RunStatus.CANCELLED
