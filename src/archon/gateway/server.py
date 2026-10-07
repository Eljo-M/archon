import asyncio
import contextlib
import hmac
import json
import logging
import math
import time
from pathlib import Path

import grpc
from prometheus_client import Counter, Histogram, start_http_server

from archon.agents.model import InferenceModel
from archon.agents.orchestrator import Orchestrator
from archon.config import Settings
from archon.db.store import RunStore
from archon.domain import Event, Issue, RepositorySpec, RunStatus
from archon.generated import archon_pb2 as pb
from archon.generated import archon_pb2_grpc as rpc
from archon.sandbox.checkout import checkout
from archon.sandbox.docker_runner import DockerRunner

RUNS = Counter("archon_runs_total", "Terminal runs", ["status"])
RUN_TIME = Histogram("archon_run_seconds", "End-to-end repair latency")
LOGGER = logging.getLogger(__name__)


def repository_from_proto(value) -> RepositorySpec:
    return RepositorySpec(value.url, value.commit_sha, value.sandbox_image,
                          tuple(value.test_argv), value.timeout_seconds)


def event_to_proto(event: Event):
    return pb.AgentProgressUpdate(stage=event.stage, current_agent=event.agent, active_diff=event.diff,
                                  is_completed=event.completed, success=event.status == RunStatus.SUCCEEDED,
                                  run_id=event.run_id, sequence=event.sequence, summary=event.summary,
                                  attempt=event.attempt, status=event.status, timestamp=event.timestamp,
                                  evidence_json=json.dumps(event.evidence))


class Gateway(rpc.AgentOrchestratorServiceServicer, rpc.ClusterCoordinatorServicer,
              rpc.SandboxServiceServicer):
    def __init__(self, settings: Settings, store: RunStore, orchestrator: Orchestrator,
                 checkout_factory=checkout):
        self.settings, self.store, self.orchestrator = settings, store, orchestrator
        self.checkout_factory = checkout_factory
        self.tasks: dict[str, asyncio.Task] = {}
        self.started: set[str] = set()
        self.nodes: dict[str, float] = {}
        self.semaphore = asyncio.Semaphore(2)

    async def authorize(self, context):
        token = dict(context.invocation_metadata()).get("authorization", "")
        expected = f"Bearer {self.settings.api_token}"
        if not self.settings.api_token or not hmac.compare_digest(token, expected):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Valid bearer token required")

    async def SubmitIssue(self, request, context):
        await self.authorize(context)
        try:
            issue = Issue(request.issue_id, request.issue_description, repository_from_proto(request.repository),
                          request.max_repair_iterations)
            issue.validate(allowed_hosts=set(self.settings.allowed_repo_hosts),
                           allowed_image=self.settings.sandbox_image)
            # Bound queued/running development jobs; distributed admission is backlog D-01.
            if len(self.tasks) >= 32:
                await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "Development job capacity reached")
            run_id, created = await self.store.create(issue, request.idempotency_key)
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        if created:
            task = asyncio.create_task(self._run(run_id, issue))
            self.tasks[run_id] = task
            task.add_done_callback(lambda _: self.tasks.pop(run_id, None))
        return pb.SubmitResponse(run_id=run_id, created=created)

    async def _run(self, run_id, issue):
        self.started.add(run_id)
        started = time.monotonic()
        try:
            async with self.semaphore:
                if (await self.store.get(run_id))["cancel_requested"]:
                    raise asyncio.CancelledError
                async with self.checkout_factory(issue.repository) as workspace:
                    await self.orchestrator.run(run_id, issue, workspace)
        except asyncio.CancelledError:
            run = await self.store.get(run_id)
            if run["status"] not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                await self.store.append(Event(run_id, 0, "CANCELLED", "gateway", "Run cancelled",
                                               status=RunStatus.CANCELLED))
        except Exception as error:
            await self.store.append(Event(run_id, 0, "FAILED", "gateway", f"Checkout stopped: {type(error).__name__}",
                                           status=RunStatus.FAILED, evidence={"category": "INFRA_ERROR"}))
        finally:
            self.started.discard(run_id)
            RUN_TIME.observe(time.monotonic() - started)
            RUNS.labels((await self.store.get(run_id))["status"]).inc()

    async def WatchRun(self, request, context):
        await self.authorize(context)
        try:
            await self.store.get(request.run_id)
            if request.after_sequence < 0:
                raise ValueError("cursor cannot be negative")
        except KeyError:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Unknown run")
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        cursor = request.after_sequence
        while True:
            events, status = await self.store.poll(request.run_id, cursor)
            for event in events:
                cursor = event.sequence
                yield event_to_proto(event)
                if event.completed:
                    return
            if status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                return
            await asyncio.sleep(0.1)

    async def DispatchIssue(self, request, context):
        submission = await self.SubmitIssue(request, context)
        async for event in self.WatchRun(pb.WatchRequest(run_id=submission.run_id), context):
            yield event

    async def CancelRun(self, request, context):
        await self.authorize(context)
        try:
            accepted = await self.store.cancel(request.run_id)
        except KeyError:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Unknown run")
        task = self.tasks.get(request.run_id)
        if accepted and task:
            if request.run_id in self.started:
                task.cancel()
            else:
                # A coroutine cancelled before its first step cannot run its own finally block.
                await self.store.append(Event(request.run_id, 0, "CANCELLED", "gateway", "Queued run cancelled",
                                               status=RunStatus.CANCELLED))
        return pb.CancelResponse(accepted=accepted)

    async def RegisterNode(self, request, context):
        await self.authorize(context)
        if (not request.node_id or not request.ip_address or not 1 <= request.port <= 65535
                or request.cpu_cores < 1 or request.gpu_vram_mb < 0):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid node capabilities")
        self.nodes[request.node_id] = time.monotonic()
        return pb.RegisterResponse(accepted=True, cluster_leader_id="archon-dev-coordinator", term=1)

    async def SendHeartbeat(self, request, context):
        await self.authorize(context)
        if (not math.isfinite(request.gpu_utilization) or not 0 <= request.gpu_utilization <= 1
                or not math.isfinite(request.memory_usage_mb) or request.memory_usage_mb < 0
                or request.active_tasks < 0):
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid heartbeat measurements")
        previous = self.nodes.get(request.node_id)
        acknowledged = previous is not None and time.monotonic() - previous <= 60
        if acknowledged:
            self.nodes[request.node_id] = time.monotonic()
        return pb.HeartbeatResponse(acknowledged=acknowledged)

    async def ExecuteTask(self, request, context):
        await self.authorize(context)
        repository = repository_from_proto(request.repository)
        try:
            repository.validate(allowed_hosts=set(self.settings.allowed_repo_hosts),
                                allowed_image=self.settings.sandbox_image)
            if not request.execution_id or len(request.git_patch.encode()) > 64_000:
                raise ValueError("execution ID is required and patch must be bounded")
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        async with self.semaphore:
            try:
                async with self.checkout_factory(repository) as workspace:
                    result = await self.orchestrator.sandbox.execute(workspace, repository,
                                                                     request.git_patch, request.execution_id)
            except Exception:
                await context.abort(grpc.StatusCode.UNAVAILABLE, "Sandbox checkout or execution failed")
        return pb.ExecutionResponse(execution_id=result.execution_id, passed=result.passed,
                                     exit_code=result.exit_code or 0, has_exit_code=result.exit_code is not None,
                                     stdout=result.stdout, stderr=result.stderr, execution_time_ms=result.execution_time_ms,
                                     status=pb.ExecutionStatus.Value(result.status), output_truncated=result.output_truncated,
                                     image_id=result.image_id)

    async def close(self):
        entries = list(self.tasks.items())
        tasks = [task for _, task in entries]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for run_id, _ in entries:
            run = await self.store.get(run_id)
            if run["status"] not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}:
                await self.store.append(Event(run_id, 0, "CANCELLED", "gateway", "Server shutting down",
                                               status=RunStatus.CANCELLED))


async def serve(settings: Settings, database: Path):
    if not settings.api_token:
        raise ValueError("ARCHON_API_TOKEN is required")
    tls_fields = [settings.tls_cert, settings.tls_key, settings.tls_ca]
    if any(tls_fields) and not all(tls_fields):
        raise ValueError("Mutual TLS requires certificate, key and CA together")
    if not all(tls_fields) and not settings.bind.startswith(("127.0.0.1:", "localhost:")):
        raise ValueError("Plaintext development gateway must bind to loopback")
    database.parent.mkdir(parents=True, exist_ok=True)
    store = RunStore(str(database))
    await store.recover_interrupted()
    model = InferenceModel(settings.model_url, settings.model_name, settings.model_api_key)
    gateway = Gateway(settings, store, Orchestrator(store, model, DockerRunner()))
    server = grpc.aio.server(maximum_concurrent_rpcs=64,
                             options=[("grpc.max_receive_message_length", 1_048_576)])
    rpc.add_AgentOrchestratorServiceServicer_to_server(gateway, server)
    rpc.add_ClusterCoordinatorServicer_to_server(gateway, server)
    rpc.add_SandboxServiceServicer_to_server(gateway, server)
    if all(tls_fields):
        credentials = grpc.ssl_server_credentials(
            [(Path(settings.tls_key).read_bytes(), Path(settings.tls_cert).read_bytes())],
            root_certificates=Path(settings.tls_ca).read_bytes(), require_client_auth=True)
        port = server.add_secure_port(settings.bind, credentials)
    else:
        port = server.add_insecure_port(settings.bind)
    if not port:
        raise RuntimeError("Failed to bind gateway")
    metrics_server, metrics_thread = start_http_server(settings.metrics_port, addr="127.0.0.1")
    try:
        await server.start()
        LOGGER.info("Archon development gateway listening at %s", settings.bind)
        await server.wait_for_termination()
    finally:
        with contextlib.suppress(Exception):
            await gateway.close()
        await server.stop(5)
        await model.close()
        store.close()
        metrics_server.shutdown()
        metrics_server.server_close()
        metrics_thread.join(timeout=2)
