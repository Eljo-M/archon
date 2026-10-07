# Archon Backlog

Checkboxes indicate implemented and locally verified work only. A foundation does not imply integration is complete. Priorities follow dependencies; revisit during weekly demos.

## Foundation

- [x] F-01 — Preserve original Protobuf numbers and add immutable execution inputs, ordered progress, idempotent submission, cancellation and explicit execution outcomes.
- [x] F-02 — Implement a persistent development run/event store and bounded repair state machine.
- [x] F-03 — Demonstrate the supplied fixture with failing original tests and passing patched tests; label scripted inference.
- [x] F-04 — Verify async gRPC submission, authentication, progress replay, disconnected watchers and cancellation.
- [ ] F-05 — Observe GitHub CI pass on Linux and Windows, then pin the validated environment.

## Execution and inference

- [ ] S-01 — Run Docker Engine integration tests for success, failure, timeout, OOM, output truncation and container cleanup.
- [ ] S-02 — Pin environment image digests and support per-repository dependency recipes.
- [ ] S-03 — Bound checkout disk/network/time consumption and add cancellation for complete Git subprocess trees.
- [ ] S-04 — Validate storage quotas, post-crash cleanup and the intended hostile-workload trust boundary.
- [ ] A-01 — Run the real model adapter with an actual endpoint; validate structured responses and provider limits.
- [ ] A-02 — Persist full model/prompt configuration and inference usage; enforce total-run token/time budgets.
- [ ] A-03 — Add semantic review and regression-test selection without permitting oracle/test tampering.

## Code intelligence

- [x] C-01 — Index bounded Python function/class symbols with Tree-sitter and safe source reads.
- [ ] C-02 — Implement framed headless LSP client with initialize/shutdown, diagnostics and server restart tests.
- [ ] C-03 — Add C++ grammar, workspace-aware symbol references and navigation quality fixtures.
- [ ] C-04 — Add revision/grammar-keyed AST cache and invalidation.

## Distributed state and services

- [ ] D-01 — Wire PostgreSQL run authority, transactional outbox, Redis Streams consumers and renewable fenced leases.
- [ ] D-02 — Prove worker crash recovery, duplicate delivery, outbox replay and stale-result rejection.
- [ ] D-03 — Build and exercise the C++ callback coordinator; integrate capabilities and worker heartbeat clients.
- [ ] D-04 — Define leadership/failover requirements and authenticated worker identity.
- [ ] D-05 — Add transport TLS client tooling, credential rotation and deployment-specific authorization.

## Evaluation, training and performance

- [ ] E-01 — Integrate official SWE-bench Lite harness and trace-to-prediction conversion; pin dataset/configuration.
- [ ] E-02 — Implement a separate isolated HumanEval evaluator and report format.
- [ ] E-03 — Publish a measured baseline with infrastructure/agent failure attribution and a declared split.
- [ ] T-01 — Validate CPU GRPO reference gradients and masking, then repeat on GPU.
- [ ] T-02 — Review verified-example exporter and dataset provenance; add split/leakage checks.
- [ ] T-03 — Implement and validate SFT/LoRA training plus checkpoint/evaluation flow.
- [ ] T-04 — Implement actual GRPO rollout grouping, executable rewards and training loop.
- [ ] T-05 — Add and benchmark custom Triton/CUDA objective kernels against the reference.
- [ ] T-06 — Measure FP8/INT4 serving on supported GPU hardware against the unquantized baseline.

## Operations and release

- [ ] O-01 — Connect Prometheus to the actual gateway and verify provisioned Grafana panels.
- [ ] O-02 — Add queue depth, leases, execution status, resource use and inference usage metrics.
- [ ] O-03 — Run C++ address/undefined-behavior sanitizers and load/fault tests in CI.
- [ ] O-04 — Rehearse deployment, upgrade, backup/recovery and installation documentation.
- [ ] O-05 — Complete release acceptance in ROADMAP.md and publish a versioned release candidate.

Next useful work: F-05 and S-01. When Docker is unavailable, proceed with C-02 and model-adapter/trace tests rather than waiting.
