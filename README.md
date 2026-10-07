# Archon

Archon turns software issues into reviewed patches and verifies them in isolated test environments. The target platform combines Python 3.12 and C++20 services, Tree-sitter/LSP navigation, asynchronous gRPC, Redis/PostgreSQL, Docker sandboxes, observable repair loops, and verified SFT/GRPO post-training.

**Current status: initial development foundation.** The repair smoke test and development gateway run today. Multi-worker scheduling, headless LSP, real model validation, GPU training/kernels and benchmark results remain in the [backlog](docs/BACKLOG.md). See the [8–12 week roadmap](docs/ROADMAP.md) and [progress log](docs/PROGRESS.md).

## Quickstart

From this repository using Python 3.12:

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -c constraints-dev.txt -e ".[dev]"
python scripts/generate_proto.py
python -m pytest -q
python -m ruff check .
python -m archon demo
```

The demo uses the shipped **trusted fixture** and scripted model responses. It records the original failing tests, the generated patch, review and passing tests in `.archon/demo.sqlite3`. It executes this controlled fixture on the host; the gateway always uses the Docker adapter for external repositories. Passing this smoke test demonstrates the orchestration path, not autonomous inference quality.

## Development gateway

Requires Docker Engine with Linux containers, Git, and an inference server implementing JSON chat completions (for example, a configured local vLLM server). Build the development execution image:

```sh
docker build -f docker/sandbox.Dockerfile -t archon-sandbox:dev .
```

Set `ARCHON_API_TOKEN`, `ARCHON_MODEL_URL` and `ARCHON_MODEL_NAME` using `.env.example` as a reference. The CLI does not automatically read `.env`; export variables into your shell or use your environment manager. Set `ARCHON_MODEL_API_KEY` when your inference endpoint requires one. Then run:

```sh
python -m archon serve
python -m archon submit path/to/issue.json
```

An issue request uses this JSON shape; replace the repository URL, immutable commit and test invocation with a repository supported by your execution image:

```json
{
  "issueId": "example-issue",
  "issueDescription": "Describe the reproducible bug",
  "maxRepairIterations": 3,
  "idempotencyKey": "one-unique-key-per-request",
  "repository": {
    "url": "https://github.com/owner/repository.git",
    "commitSha": "replace-with-a-full-40-character-lowercase-sha",
    "sandboxImage": "archon-sandbox:dev",
    "testArgv": ["python", "-m", "unittest", "discover", "-s", "tests"],
    "timeoutSeconds": 120
  }
}
```

The gateway listens on loopback port 50051 with bearer authentication. Mutual TLS is available through `ARCHON_TLS_CERT`, `ARCHON_TLS_KEY`, and `ARCHON_TLS_CA`; all three are required together. The supplied CLI currently supports the plaintext loopback development endpoint. `SubmitIssue` creates a durable run; `WatchRun` supports ordered replay; cancelling a watcher does not cancel its job. Use `CancelRun` to cancel the job explicitly. Incomplete development jobs are marked failed on restart rather than silently resumed.

The default runner applies source-only Python patches to a fresh snapshot, then runs argv directly in a disposable container with no network, no host mounts, no Docker socket, an unprivileged UID, dropped capabilities, CPU/memory/process limits and bounded logs. Timeout/cancellation triggers container cleanup. Storage quotas and crash cleanup require further integration work; the current adapter is not a validated hostile multi-tenant execution boundary. Repository environments must contain their test dependencies before running; runtime network installation is disabled.

## Infrastructure

```sh
docker compose up -d
```

This provisions Redis, PostgreSQL, Prometheus and Grafana for development. PostgreSQL bootstrap applies the schema only on a new data volume; `archon.db.postgres.migrate` is available for explicit migration application. Redis Streams and PostgreSQL foundations are not yet wired into the development gateway, which uses SQLite. Prometheus/Grafana provisioning exists; host metrics forwarding and real dashboard validation are tracked in O-01. Compose credentials are local-development defaults and can be overridden through environment variables.

## C++ coordinator

The C++20 callback service implements authenticated registration and heartbeats at `127.0.0.1:50052`, using the same Protobuf contract. It is a single-coordinator prototype with in-memory node records; term 1 is not a distributed consensus claim.

Install CMake, a C++20 compiler, Protobuf and gRPC development packages, then:

```sh
cmake -S . -B build -DARCHON_SANITIZERS=ON
cmake --build build --parallel
# Set ARCHON_API_TOKEN before starting.
./build/archon-coordinator
```

## Training and evaluation

`src/archon/training/grpo.py` contains a reference clipped token-level objective and detached group-normalized rewards. CPU tests cover gradients, clipping inputs, group normalization and completion masks; GPU validation is pending. Install PyTorch from its appropriate CPU/CUDA index to run these tests. Full rollout/SFT/GRPO training, CUDA/Triton kernels and quantized serving are scheduled work, not implemented results. `distill.export_verified` exports verified patch examples and excludes scripted fixture runs; dataset review and split controls remain required before training.

SWE-bench Lite repository repair and HumanEval function completion will be evaluated separately. No benchmark scores or training improvements have been measured yet.

## Repository map

```text
proto/archon.proto                 Shared service contract
src/archon/gateway/                Python asynchronous development gateway
src/gateway/cpp/                   C++20 callback coordinator
src/archon/agents/                 Architect/Coder/Reviewer repair loop
src/archon/codegraph/              Tree-sitter Python navigation
src/archon/sandbox/                Docker Engine adapter, checkout and patch validation
src/archon/db/                     Development store, Redis adapter and PostgreSQL schema
src/archon/training/               Reference GRPO and verified-example export
docker/                           Execution image
observability/                    Prometheus/Grafana development configuration
examples/                         Controlled failing repository and repair patch
tests/                            Behavioral tests and RPC integration fixtures
docs/                             Roadmap, backlog and actual progress
```

Implementation references: [gRPC AsyncIO](https://grpc.github.io/grpc/python/grpc_asyncio.html), [gRPC C++ callbacks](https://grpc.io/docs/languages/cpp/callback/), [Docker Engine SDK](https://docker-py.readthedocs.io/en/stable/containers.html), [Tree-sitter Python bindings](https://github.com/tree-sitter/py-tree-sitter), and [GRPO reference documentation](https://huggingface.co/docs/trl/grpo_trainer).
