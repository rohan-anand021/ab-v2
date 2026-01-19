# Plan: Pythonize the Sandbox Workflow

Goal: Replace ad-hoc shell scripts with a Python-driven sandbox controller that can start/stop long-running containers, clone/checkout repos, install task-specific deps, and run baseline tests with clear, typed interfaces.

## Architecture
- `SandboxConfig` (Pydantic): image, container name, workdir, env, timeout defaults, resource limits.
- `RepoSpec` (Pydantic): repo URL/path, commit/ref, optional patches/compat steps.
- `TaskSpec` (Pydantic): setup commands, test command (baseline), expected_fail (bool), env overrides.
- `SandboxClient`: thin wrapper around `subprocess` to call `docker run/exec/cp/stop/rm`; isolated helper per operation.
- `SessionManager`: orchestrates lifecycle: start container → clone/checkout → apply compat rewrites → run setup → run tests → collect results.
- `Result` models: `CommandResult` (stdout/stderr/exit), `StageResult` (stage name, status, logs), `RunReport` (aggregate). Keep every Pydantic model under `sandbox/models/` to centralize validation and reuse.
- Event-based logging via a JSONL logger (emit stage/context/data); wire it into docker client and session runner.

## Modules / Files
- `sandbox/models/`: Pydantic models (`SandboxConfig`, `RepoSpec`, `TaskSpec`, result structs).
- `sandbox/docker_client.py`: subprocess helpers for docker {run,exec,cp,stop,rm,ps}, with timeouts and structured results.
- `sandbox/session.py`: high-level workflows (prepare_repo, apply_compat, run_setup, run_tests).
- `sandbox/compat.py`: reusable fixes (collections.abc rewrites, setuptools caps, pytest bumps, warning suppression).
- `sandbox/report.py`: serialization of `RunReport` to JSON/YAML for artifacts.
- `scripts` entrypoints: `python -m sandbox.run_smoke --config path/to/smoke.yaml` (replaces shell scripts).

## Workflow
1) Load config (e.g., JSON/YAML with one instance) into Pydantic models.
2) Start container (`docker run -d`) per `SandboxConfig`.
3) Clone repo (`docker exec git clone`) and checkout commit.
4) Apply compat patches (collections.abc rewrite, optional warning/env tweaks).
5) Run setup commands (in order), capture outputs, stop on first failure.
6) Run baseline test command, capture exit/outputs; assert expected_fail.
7) Stop and remove container; write `RunReport`.

## Output capture plan
- Central command runner returns `CommandResult` (cmd, cwd, env, exit, stdout, stderr, duration, timestamp).
- `StageResult` aggregates related commands (clone, checkout, compat, setup, test).
- `RunReport` holds ordered `StageResult`s plus summary (success/failure reason).
- Write a single NDJSON or JSON file (e.g., `run_report.json`) with all stages and command outputs; keep raw stdout/stderr inline for simplicity, or truncate with a max size if needed.
- Optionally mirror stdout/stderr to per-command log files under `artifacts/` if size is a concern, then have a consolidation script that:
  - reads per-command logs,
  - applies size caps/truncation,
  - emits a unified report (JSON/NDJSON) with pointers to truncated files.
- Consider a lightweight context manager to append `CommandResult` to an in-memory list and flush to JSON at the end; avoid complex logging frameworks.

## Design Principles
- Strong typing via Pydantic; fail fast on bad configs.
- Pure Python subprocess (no docker SDK), centralized `run_command()` with timeout, env, cwd, stream capture.
- Clear separation: low-level docker ops vs orchestration vs compatibility heuristics.
- Deterministic logging: per-stage stdout/stderr saved to artifacts folder.
- Extensible: plug in new compat fixes and repo-specific heuristics.

## Next Steps
- Scaffold modules/files above.
- Port existing shell smoke logic into `SessionManager` flows.
- Add CLI entrypoint(s) for: session smoke, local clone/checkout smoke, SWE-bench-lite single-instance smoke.
- Add tests for `run_command` and compat helpers (unit), plus a mocked session test.
