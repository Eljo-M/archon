# Archon development instructions

The user authorized starting the whole Archon project, daily meaningful tested commits and pushes to the public GitHub repository https://github.com/Eljo-M/archon, with Codex leading almost all implementation. The agreed target is approximately 8–12 weeks from October 6, 2026 (December 1–29). This is a delivery target, not permission to fabricate completion or benchmark scores.

Read docs/ROADMAP.md, docs/BACKLOG.md and the most recent entries in docs/PROGRESS.md before choosing work. Complete the next useful bounded increment and preserve unrelated user edits. Use existing project conventions. Prefer additive compatible Protobuf changes.

Run relevant tests and lint before committing. Publish meaningful changes; do not create empty commits to simulate activity. Never force-push, overwrite a changed remote head, commit credentials, or hide failing checks. Commit messages must describe the actual change. Daily commits and pushes are authorized; creating paid infrastructure or purchasing GPU capacity requires explicit user instructions.

Use a `codex/` prefix for new development branches. The bootstrap may be published to the repository's existing main branch; subsequent work should use the configured development branch or an appropriate codex branch. Opening draft PRs is permitted within the implementation scope. Record actual verification and remaining limitations.

The trusted fixture runner is for tests and the supplied demonstration only. Never expose host execution through RPC or use it for external repositories. Repository tests and model patches run in the Docker executor. Model internal reasoning is not persisted; retain concise summaries, tool observations and verifiable results.

The initial gateway uses a single-process SQLite development store. Redis Streams and PostgreSQL foundations exist but are not yet wired into the worker lifecycle. Do not call this implementation distributed or production-ready until backlog D-01 and D-02 pass real fault-injection tests.

GPU kernels, SFT training, full SWE-bench evaluations and deployment acceptance must be validated on actual available infrastructure. Mark unavailable checks explicitly. Do not invent test passes, training runs, model improvements or benchmark results.

Daily development starts once per night at a randomly selected slot between 8:17 PM and 2:17 AM America/New_York, weighted toward 8–11 PM. The heartbeat checks hourly within that window; the local scheduling helper in this chat's work folder claims at most one session for the evening and its following overnight period. Follow the heartbeat's gate before beginning scheduled work. A missed slot may start at a later check within the window when the computer and app are available. October 6 is already marked completed. Report meaningful committed progress, milestone completion, failures or needed user action; avoid repeating unchanged blockers when independent useful work is unavailable.
