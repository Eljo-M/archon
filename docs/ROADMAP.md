# Archon — 8–12 Week Delivery Roadmap

Start: October 6, 2026. Target delivery window: December 1–29, 2026. Owner: Codex leads implementation; Eljo-M supplies repository, runtime/model access, compute and product decisions. Work is sequenced for one primary implementer. The original seven-engineer allocation is a map of workstreams, not a claim that seven engineers are staffed.

The twelve-week schedule is the planning baseline. An eight-week release is a stretch target that requires the core milestones to pass early; it must not be achieved by dropping required verification or claiming unbuilt components are complete.

| Week | Dates | Outcome | Exit evidence |
|---|---|---|---|
| 1 | Oct 6–12 | Contracts, repository, CI, persistent development traces and repair fixture | Baseline fails, reviewed patch passes, retries/cancellation/replay tested |
| 2 | Oct 13–19 | Docker executor integrated with real model inference | Real container failure, patch, pass, timeout, output-bound and cleanup checks |
| 3 | Oct 20–26 | Tree-sitter navigation plus headless LSP | Python/C++ symbol and diagnostic fixtures; server-crash/restart behavior |
| 4 | Oct 27–Nov 2 | PostgreSQL authority and Redis queue/outbox | Atomic submit and publish recovery; lease fencing and replay |
| 5 | Nov 3–9 | Multi-worker gRPC scheduling and C++ integration | Worker loss, stale result, duplicate delivery and cancellation fault tests |
| 6 | Nov 10–16 | Agent quality, budgets and useful telemetry | Bounded runs on a declared development set; cost/latency and failure reporting |
| 7 | Nov 17–23 | SWE-bench Lite and separate HumanEval harnesses | Reproducible baseline reports from pinned datasets/configurations |
| 8 | Nov 24–30 | SFT/LoRA data pipeline and small validated training run | Dataset split integrity, checkpoint provenance and held-out comparison |
| 9 | Dec 1–7 | GRPO training with verifiable execution rewards | Validated objective/gradients, reward oracle, reproducible training/eval |
| 10 | Dec 8–14 | Triton/CUDA optimization and quantized serving | Reference agreement and measured performance/quality on supplied GPU |
| 11 | Dec 15–21 | Reliability, load, isolation and deployment hardening | Sustained load, restart/cleanup tests and documented trust boundary |
| 12 | Dec 22–28 | Release candidate, benchmark report and handover | All acceptance checks, installation rehearsal, versioned artifacts |

## Daily development loop

1. Inspect the working tree, recent commits, CI and progress log.
2. Select the next task whose dependencies are available. Work through a coherent increment.
3. Validate the changed behavior with focused tests, then the required project checks.
4. Update the backlog and progress log with actual evidence and limitations.
5. Commit and push the tested change to the authorized repository. A blocked day does not require an empty commit.
6. Report meaningful progress or a new blocker; continue independent work when one dependency is unavailable.

At each weekly boundary, demonstrate the current integrated system and adjust estimates using the observed results. If a required dependency threatens the delivery window, identify it early with a concrete next action.

## Release acceptance

- A documented fresh installation can run authenticated services, provision the infrastructure and reproduce a repair.
- Multiple workers execute tasks with durable PostgreSQL state, Redis delivery recovery, leases and stale-result fencing.
- Code navigation uses Tree-sitter and a headless LSP with bounded context and clean process lifecycle.
- Architect/Coder/Reviewer loops obey repair, time and inference budgets and produce replayable evidence.
- Repository execution is isolated with tested resource limits, bounded output, cancellation and cleanup; the deployment trust boundary is documented.
- SWE-bench Lite and HumanEval have separate reproducible reports and held-out evaluation. Agree quality thresholds after the baseline; no target score is currently promised.
- SFT/LoRA and GRPO pipelines run on supplied hardware with checkpoint/dataset provenance and verified test rewards.
- Custom Triton/CUDA work agrees with the reference objective and demonstrates a measured benefit; INT4/FP8 serving has a recorded quality/resource comparison on compatible hardware.
- CI, memory sanitizers, migrations, dashboards, operational runbooks and release artifacts pass their required checks.

## Dependencies to supply

Docker Engine with Linux containers; C++20/CMake and gRPC development libraries; a model-serving endpoint and model identifier; a Linux NVIDIA GPU runtime with GPU model/VRAM details; training/evaluation dataset access; and an agreed deployment destination. Use environment variables or a secret manager for credentials, never committed files.

The daily local schedule depends on the computer and desktop app being available, the checkout remaining on disk, and the necessary permissions and account limits. See the [official scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).
