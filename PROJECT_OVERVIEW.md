# AgentBench – Detailed Project Overview

This document walks through the repository in depth: layout, key modules, class/function roles, CLI behavior, sandboxing, tooling, tasks, reporting, scripts, and vendored extras.

## Repository Snapshot (truncated tree)
```
agentbench
├── .conductor
├── .coverage
├── .env
├── .env.example
├── .github
│   └── workflows
│       └── test.yml
├── .gitignore
├── .gitmodules
├── .python-version
├── .ruff_cache/
├── .uv_cache/
├── README.md
├── agentbench
│   ├── __init__.py
│   ├── agent_runner.py
│   ├── agents/
│   │   ├── base.py
│   │   ├── llm_v0.py
│   │   ├── loop.py
│   │   ├── observation.py
│   │   ├── prompts/system_v1.py
│   │   ├── scripted.py
│   │   ├── tests/*.py
│   │   └── types.py
│   ├── cli.py
│   ├── config.py
│   ├── llm/
│   │   ├── client.py, config.py, errors.py, messages.py, openrouter.py, tests/
│   ├── logging.py
│   ├── reporting/
│   │   ├── cli.py, inputs.py, models.py, render.py, summary.py, templates.py, tests/
│   ├── run_task.py
│   ├── sandbox/
│   │   ├── docker_sandbox.py, filesystem.py, models.py, persistent_sandbox.py, tests/
│   ├── schemas/
│   │   ├── README.md, attempt_record.py, events.py, tests/
│   ├── scoring/
│   │   ├── README.md, taxonomy.py, tests/
│   ├── suite_runner.py
│   ├── tasks/
│   │   ├── exceptions.py, loader.py, models.py, validation.py, validator.py, tests/
│   ├── tests/*.py
│   ├── tools/
│   │   ├── README.md, builtins.py, contract.py, patch_models.py, patching.py, schemas/events.py, tests/
│   └── util/
│       ├── attempt.py, commands.py, events.py, git.py, jsonl.py, paths.py, process.py,
│       ├── timeout.py, truncation.py, tests/
├── configs/
├── docker/py-runner/Dockerfile, README.md
├── examples/toy_repo/{src/toy/mathy.py, tests/test_basic.py, pyproject.toml}
├── external/
│   ├── python-ai-sdk-sdk/ (vendored SDK with docs, examples, tests)
│   └── snitchbench/ (TypeScript analysis utilities)
├── main.py
├── plan/ (design docs)
├── private/PROJECT_OVERVIEW.md
├── scripts/*.py|*.sh
├── tasks/
│   ├── custom-dev/*/task.yaml
│   ├── swe-bench-lite-demo/psf__requests-1963/task.yaml
│   ├── swe-bench-lite-10/*/task.yaml
│   └── swe-bench-lite-new/*/task.yaml
├── pyproject.toml, uv.lock, pyproject.toml.backup, pyrefly.toml
└── venv/
```

## Top-Level Entry Points
- `main.py`: trivial “Hello from agentbench!” script.
- `pyproject.toml`: Poetry/uv metadata, dependencies (pydantic, typer, rich, httpx, yaml, filelock, ulid, pytest, ruff, etc.), console script entry `agentbench=agentbench.cli:app`.
- `README.md`: high-level intro, task spec, CLI usage, and system behavior.
- `.github/workflows/test.yml`: CI pipeline using uv cache + pytest (`uv run pytest --disable-warnings --maxfail=1`), python version pinned via `.python-version`.

## CLI (`agentbench/cli.py`)
- Typer app exposing:
  - `run-task`: run a single task YAML, cloning repo, running setup, then task command; writes artifacts under `artifacts/runs/<timestamp>__<ulid>/`.
  - `run-agent`: run scripted or LLM agent on one task; manages workspace/artifacts dirs, optional strict patch mode, LLM config injection; prints summary table; exits non-zero on failure.
  - `run-agent-suite`: iterate over all tasks in a suite, per-task workspace/artifact dirs under `artifacts/suite_runs/<suite>/<task_id>/`.
- `validate-suite`: baseline-validate all tasks in a suite (fail if tests pass); skips `flaky` by default.
- `list-tasks`: enumerate task IDs in a suite.
- Uses `setup_logging()` globally; handles OpenRouter key/model for `llm_v0`; cleans workspaces before runs.
- Exit behavior: `run-agent` exits 1 when the attempt fails or variant misconfigures; `validate-suite` exits 1 on missing suite; `list-tasks` exits 0 with warning if no tasks found.

## Execution Pipeline
- **run_task.py**: core executor for baseline runs.
  - Resolves repo URLs (supports relative/file URLs), inspects Docker image metadata, prepares artifact paths.
  - Supports sandbox modes `bind` (host workspace volume) and `ephemeral` (PersistentDockerSandbox).
  - Performs git clone/checkout (`clone_repo`, `checkout_commit` or sandbox variants), runs setup commands (normalized pip installs), captures diff/stat/status, env info, executes test command with network none/bridge, writes logs to `logs/`.
  - `run_network` switches to `bridge` when task labels include `network` (otherwise `none`); captures environment info (uname/python/pip/pytest versions) after setup.
  - Uses `DockerSandbox` (single-run containers) or `PersistentDockerSandbox` (long-lived container) depending on sandbox mode.
  - Returns path to run directory containing task copy, logs, workspace, and run metadata.
  - Helper functions: `_inspect_docker_image` records image ID/repo digests; `_resolve_repo_url` resolves relative/file URLs; `_inspect_docker_image` handles parse errors/timeouts; `_resolve_repo_url` searches up directory tree for relative paths.
- **suite_runner.py**: orchestrates baseline validation across suites with rich progress UI, SIGINT handling, skip labels; writes run.json and attempts.jsonl summary.
- **agent_runner.py**: orchestrates full agent attempt.
  - Optional baseline validation via `validate_baseline`; otherwise clones and checks out repo directly.
  - Builds sandbox, instantiates agent (`ScriptedAgent` or `LLMAgentV0`), wires `EventLogger`, budgets, and artifacts.
  - Maps stop reasons to `FailureReason`, logs agent-finished event, returns populated `AttemptRecord` (duration, failure reason, stop reason, artifacts list).
  - `_resolve_repo_url` handles relative/file URLs; `_get_agent` enforces llm config presence for `llm_v0`; skips `sandbox_mode=ephemeral` (not supported for agents).
  - `run_id` is ULID; `EventLogger` enabled for non-scripted agents by default; `AgentBudget` derived from task.agent (steps) and `max(task.environment.timeout_sec, 180)` for time.
  - Artifact paths include comma-joined list of applied patches; `limits` filled from task environment timeout.

## Agents
- **agents/base.py**: abstract `Agent` interface with `variant_name`, `decide(state)`, and `format_observation(state)`.
- **agents/types.py**: Pydantic models/enums for `AgentBudget` (step/time/patch limits), `AgentState` (tool history, budgets, last test output), `AgentAction` (tool call vs stop), `StopReason`, and `AgentResult`.
- **agents/loop.py**: decision loop runner.
  - Runs initial setup/tests; auto-success if tests already pass.
  - Enforces budgets, repeated-failure detection, and automatic final test runs before exit.
  - Executes tool requests via builtins/patching/run_tool, auto-runs tests after successful patches, auto-runs tests on exit if needed.
  - Tracks `_setup_completed`, `_tests_ran_since_last_patch`; ensures only real test commands count for success (via `_is_test_command`).
  - Logs tool/test events through `EventLogger`; catches SIGINT via `interruptible` context.
  - Key methods: `_run_initial_tests` (setup + first pytest), `_execute_tool` (dispatch, auto-setup rerun for test commands, auto-run after patches), `_update_state` (updates budgets, history, last outputs), `_check_stop_conditions` (success, budgets, repeated failures), `_ensure_final_tests` (auto-run tests if patches not verified).
  - Repeated-failure guard: compares recent RUN outputs; if N latest identical, stops with `StopReason.REPEATED_FAILURE`.
- **agents/llm_v0.py**: tool-using LLM agent.
  - Builds observation string (task id, budgets, last test output, recent tool history).
  - Uses `LLMClient` to call OpenRouter Responses API with tool definitions for list/read/search/apply_patch/run.
  - Parses tool calls or unified diffs; queues multiple tool calls; retries once on malformed JSON args (`ToolCallFormatError`).
  - Fallback strategy: pick unread file from last `list_files` result if no tool calls returned.
- **agents/scripted.py**: deterministic agent for toy tasks.
  - Fixed sequence: list Python files → read `src/toy/mathy.py` → search `def add` → apply hardcoded patch to `add` → run pytest with proper PYTHONPATH.
  - Uses `EventLogger`, respects setup, runs quick initial tests for early success.
- **agents/prompts/system_v1.py**: LLM system prompt string plus SHA-tag helper; emphasizes minimal, precise patches, unified diff format, always respond with tool calls.
- **agents/observation.py**: helper utilities/tests for formatting observations and summarizing tool results for logging; validates truncation logic used by `AgentLoop`.

## Tools API
- **tools/contract.py**: Tool enums/models (`ToolName`, `ToolRequest`, param models, `ToolResult` with timestamps/paths/errors).
- **tools/builtins.py**:
  - `list_files`: safe glob inside workspace (blocks escapes/symlinks, filters hidden); returns relative paths.
  - `read_file`: safe path resolution, directory listing fallback, truncates large files, suggests candidates if missing, handles binary errors.
  - `search`: ripgrep JSON parsing with context, max_results cap, timeout handling, regex vs fixed-strings.
  - `run_tool`: executes shell command in DockerSandbox, default network none, captures stdout/stderr to `logs/tool_step_XXXX_*`, truncates large logs unless `AGENTBENCH_FULL_LOGS`.
- **tools/patching.py**: robust patch application.
  - Accepts unified diff, Begin Patch, or context-style diffs; optional strict mode (`AGENTBENCH_STRICT_PATCH`).
  - Normalizes headers, paths, hunk counts, newline markers; prevents workspace escapes; supports repo/src path adjustments.
  - Uses `patch` with dry-run fallback, context patch fallback, Begin Patch parsing (update/add/delete/move).
  - Writes patch artifacts `diffs/step_NNNN.patch`; returns changed files and patch size.
- **tools/patch_models.py**: dataclasses for `PatchHunk`/`FilePatch`.
- **tools/schemas/events.py**: event schema for tool-level logging; matches fields used in reporting tests.
- **tools/tests**: assert path-escape protections, Begin Patch parsing, patch normalization, ripgrep search parsing, and schema compatibility with event logging.
- **tools/README.md**: documents exposed tool APIs and contract for agents; mirrors `ToolName`/params used in prompts.

## Sandbox & Safety
- **sandbox/docker_sandbox.py**: thin wrapper over `docker run` with hardening (cap-drop, no-new-privileges, PID limit, tmpfs /tmp); supports network none/bridge; enforces workspace existence; env defaults set.
- **sandbox/persistent_sandbox.py**: long-lived container with optional tmpfs workspace; supports docker exec, copy to/from, network toggling, cleanup; used for ephemeral sandbox mode.
- **sandbox/filesystem.py**: safe path resolution (`resolve_safe_path`, `safe_glob`); prevents path escapes/symlinks, handles `/workspace` and `/workspace/repo` prefixes; raises `PathEscapeError`, `SymLinkError`.
- **sandbox/models.py**: `DockerRunResult` dataclass.

## LLM Integration
- **llm/config.py**: `LLMConfig` with provider info (`LLMProvider.OPENROUTER`), sampling params (temperature/top_p/max_tokens/stop), retry policy.
- **llm/client.py**: abstract `LLMClient` with `complete` and token counting.
- **llm/openrouter.py**: HTTPX-based client for OpenRouter Responses API.
  - Builds request body with messages/tools, handles headers with API key, retries per policy, classifies HTTP errors to `LLMErrorType`, logs via `EventLogger`, token counting via char heuristic.
  - Request payload fields: `model`, `input` (list of normalized `InputItem` dicts), `max_output_tokens`, `temperature`, `top_p`, optional `tools` + `tool_choice="auto"`.
  - Error classification: 401/402/403 → AUTH_FAILED, 429 → RATE_LIMITED (retryable), 5xx → PROVIDER_ERROR, timeouts → TIMEOUT, malformed JSON → INVALID_RESPONSE.
- **llm/messages.py**: Pydantic models for Responses API messages, tool/function calls, token usage; normalizes chat-completions style payloads; helpers `.has_tool_calls`, `.text_content`, `.tool_calls`.
- **llm/errors.py**: `LLMError` hierarchy (RateLimited, Authentication, Timeout, ContextLength, InvalidRequest, ProviderError, ContentFilter) mapped to `FailureReason.LLM_ERROR`.
- **config.py**: `AgentBenchSettings` (env prefix `AGENTBENCH_`), default model/provider (`default_model="mistralai/devstral-2512:free"`, `default_provider=OPENROUTER`), artifact/task/prompt dirs; `get_api_key_for_provider` helper.
- Environment knobs affecting LLM: `OPENROUTER_API_KEY` (required for llm_v0), `MODEL_NAME` override, `AGENTBENCH_LOG_LLM_MESSAGES`/`AGENTBENCH_LLM_LOG_MAX_CHARS` control logging/truncation, `AGENTBENCH_STRICT_PATCH` influences patch normalization.

## Tasks & Validation
- **tasks/models.py**: Pydantic specs for repo/environment/setup/run/validation/agent/task; serializes source_path; `ValidationResult` model for baseline validation.
- **tasks/validation.py**: schema validation for task YAML (supports `task_spec_version` 1.0); type checks, regex validation, harness version guard.
- **tasks/validator.py**: baseline validator.
  - Resolves repo URL, clones/checks out (bind or ephemeral sandbox), runs normalized setup (enforced clean tree unless `enforce_clean_setup` false), runs test command, enforces failure expectation (exit codes, regexes, failing tests).
  - Computes failure signature, reruns tests if time remains to detect flakiness, captures artifacts (status/diff/diff_stat), maps to `FailureReason` taxonomy, writes `AttemptRecord` via `AttemptContext`.
- **tasks/loader.py**: load task YAML → `TaskSpec` (with validation), discover tasks, load suite (skip invalid tasks gracefully).
- **tasks/exceptions.py**: `InvalidTaskError`, `SuiteNotFoundError`.
- **tasks/tests/**: coverage for models, loader, validator, validation schema.
- **Task spec nuances**: `labels` gate skip logic and allow `network` label to request bridge network during `run`; `agent.max_steps` feeds `AgentBudget`; `validation.enforce_clean_setup` can allow dirty worktrees after setup.
  - Harness version check: `harness_min_version` compared against installed agentbench version (when packaged); rejects tasks requiring newer harness.
- **Task data (`tasks/`):**
  - `custom-dev`: toy tasks (fail, pass, timeout, setup failure, one-liner) using `examples/toy_repo`.
    - `toy_fail_pytest`: pytest fails due to incorrect `toy.mathy.add` implementation; setup installs pytest and package into `/workspace/site-packages`; agent entrypoint default `llm_v0`.
    - `toy_timeout`: uses runner image `ghcr.io/agentbench/py-runner:0.1.0`, short timeout (5s) with run command `sleep 60 && pytest -q` to trigger timeout behavior.
    - `toy_setup_fail`: intentionally broken setup (see task YAML) to exercise `SETUP_FAILED`; `toy_one_liner` and `toy_pass_pytest` cover passing baselines and trivial tasks.
  - `swe-bench-lite-demo`: single `psf__requests-1963`.
  - `swe-bench-lite-10`: 10 tasks across seaborn/flask/requests.
  - `swe-bench-lite-new`: 10 tasks across astropy/django.
  - Each `task.yaml` specifies repo URL/commit, docker image (e.g., python:3.11-slim), workdir `/workspace`, timeout, setup commands, run command (pytest), optional agent entrypoint/max_steps, labels (`toy`, `network`, `flaky`).

## Scoring & Failure Taxonomy
- **scoring/taxonomy.py**: `FailureReason` enum with precedence and helpers:
  - `from_pytest_exit_code`, `from_stage`, precedence mapping (git errors > setup > baseline > sandbox > LLM > tools > timeout > agent gave up > tests failed).
- **scoring/README.md**: human-readable taxonomy documentation.

## Schemas & Events
- **schemas/attempt_record.py**: Attempt record schema v0.1.0 with timestamps, baseline validation info, task result (failure_reason/stop_reason), variant/model config, limits, artifact paths; includes serializer for datetimes.
- **schemas/events.py**: event types for tool/test/command/LLM/task lifecycle; `Event` model with event_version 1.0.
- **schemas/README.md**: schema guidance.

## Reporting
- **reporting/cli.py**: `agentbench report summary` subcommand; loads run dir, computes summary, renders markdown + CSV (summary + attempts), supports strict/warnings handling.
- **reporting/inputs.py**: validates expected files (run.json, attempts.jsonl), normalizes attempts (`NormalizedAttempt`), collects warnings for malformed records.
- **reporting/models.py**: data models for report warnings, metadata, normalized attempts, overview metrics, failure buckets, hardest tasks, report summary.
- **reporting/summary.py**: aggregates pass rate, median/p95 durations, failure histogram, hardest tasks (highest failure rate + duration), percentiles helper.
- **reporting/render.py & templates.py**: string renderers for markdown table summary and CSV exports; templates define Markdown sections (Overview, Failure Histogram, Hardest Tasks) with percentage formatting and table headers used in tests.
- **reporting/tests/**: deterministic rendering, inputs validation, summary calculations.
- Key reporting behaviors:
  - `expected_paths` lists required/optional files (`run.json`, `attempts.jsonl`, optional events/markdown/csv outputs).
  - `read_attempts_jsonl` tolerates malformed lines, returns warnings and invalid line count; `normalize_attempt` fills missing suite/variant from run metadata when possible.
  - CSV renders include attempts with model names and artifact paths when present.

## Utilities
- **logging.py**: basic logging formatter for `agentbench` namespace; sets level, attaches stderr handler, disables propagation to avoid duplicate logs.
- **util/commands.py**: normalize pip install commands to persist in `/workspace/site-packages` (adds `--target/--upgrade/--force-reinstall` unless editable).
- **util/truncation.py**: line/byte truncation helpers with limits (`MAX_OUTPUT_BYTES=100k`, `MAX_OUTPUT_LINES=2000`).
- **util/timeout.py**: `with_timeout` decorator using SIGALRM; default tool timeouts map (`TOOL_TIMEOUTS`).
- **util/process.py**: run command with logging, timeout handling; `check_exit_code`.
- **util/git.py**: clone/checkout/status/diff helpers; sandbox variants using docker exec; install git inside sandbox if missing.
- **util/jsonl.py**: append/read JSONL with file locks and robust error handling.
- **util/events.py**: `EventLogger` and `NullEventLogger` for structured event/LLM logging with truncation.
- **util/attempt.py**: `AttemptContext` context manager ensuring AttemptRecord is written even on crashes/interrupts.
- **util/paths.py**: `ensure_dir` helper used across sandbox/git/runner code to create directories idempotently.
- **util/truncation.py** and **util/timeout.py**: shared constants; SIGALRM timeout decorator used by tools; truncation keeps head/tail markers and reports lines omitted.
- **util/tests**: cover git helpers, path handling, truncation correctness, command exit code handling, timeout behavior, JSONL parsing, and event payload structures.
- Event logging details: `EventLogger` writes one line per event with `event_version`, `event_type`, timestamp, run_id, step_id, and payload; `log_llm_messages` writes request/response/error pairs with configurable truncation; tool results also mirrored to `llm_messages.jsonl` when logging enabled.

## Reporting & LLM Logging Behavior
- Events file: `events.jsonl` (tool starts/finishes, agent turns, tests start/finish, patches, LLM request lifecycle).
- Optional `llm_messages.jsonl` when `--log-llm-messages` or `AGENTBENCH_LOG_LLM_MESSAGES`; truncates payloads via env `AGENTBENCH_LLM_LOG_MAX_CHARS`.
- Artifacts: per-run directories under `artifacts/runs`, `artifacts/agent_runs`, `artifacts/suite_runs`, diff files under `diffs/`, logs per step under `logs/`.

## Sandboxing & Task Execution Notes
- `DockerSandbox.run`: enforces network none/bridge, read-only FS when network none, mounts workspace at `/workspace`, hardened flags (`--cap-drop=ALL`, `--security-opt no-new-privileges`, PID limit, tmpfs /tmp).
- Persistent sandbox enables ephemeral mode for run_task/validate baseline with tmpfs workspace; ensures git availability via package managers if missing.
- Path safety: `resolve_safe_path` strips `/workspace/repo` prefixes, prevents escapes/symlinks; tools use this for all file access.

## Scripts (`scripts/`)
- `benchmark_models.py`: benchmark multiple models on a task; optional docker image override, per-model artifacts, baseline check helper, reads `scripts/models.txt` (filtered to kimi/claude defaults).
- `find_and_benchmark.py`, `import_swebench.py`: dataset/model benchmarking helpers.
- `doctor.sh`: checks Docker availability, runner image presence, network isolation, and runs smoke task.
- `sanity_check_agent.sh`: small sanity run for agent; `demo_scripted_agent.sh`: runs scripted agent on toy task end-to-end.
- `openrouter_call.py`: sample OpenRouter invocation; `check.sh`: CI helper.

## Docker Runner
- `docker/py-runner/Dockerfile`: hardened Python runner image (base python:3.11-slim); installs build-essential/git, creates non-root user, sets up UV, pip cache dirs, and entrypoint for sandbox runs.
- `docker/py-runner/README.md`: usage/flags description.

## Examples
- `examples/toy_repo`: simple package `toy.mathy.add` with tests; used by `custom-dev` toy tasks and scripted agent; pyproject defines package metadata and pytest dependency.

## External Vendored Code
- `external/python-ai-sdk-sdk`: vendored SDK with docs/examples/tests for AI SDK (OpenAI/Anthropic tooling); not used by core harness but available.
- SDK contents: `src/ai_sdk` (agent, generate_text/object, tool calling providers for OpenAI/Anthropic), `docs/` (MDX API docs, examples, provider notes), `examples/*.py` demonstrating streaming, tool calling, embeddings; `tests/` exercising embedding/tool calling.
- `external/snitchbench`: TypeScript utilities and prompts for “snitchbench” analysis; not referenced by main code.

## Plan & Private Notes
- `plan/`: design documents (weekly notes 1–12, specs, diagrams, migration plans, abstraction alternatives, docker ephemeral specs, inference-server specs, RL integration notes).
- `private/PROJECT_OVERVIEW.md` and auxiliary JSON/text data in `private/` (jobs list, reasoning notes).

## Tests
- Extensive pytest coverage across agents (loop/stop conditions/prompts), llm (config/errors/messages), sandbox, schemas, scoring taxonomy, tasks, tools, reporting, and CLI workflows (run_task, suite_runner, benchmark_models).
- Test data fixtures under `reporting/tests/fixtures`, sandbox temp dirs, etc.
- Root `agentbench/tests/`: end-to-end checks for CLI, suite runner, run_task, attempt record writing, logging, persistent sandbox, stop-reason mapping, and benchmark_models script behavior.

## Settings & Environment
- Environment variables of note: `OPENROUTER_API_KEY`, `MODEL_NAME`, `AGENTBENCH_STRICT_PATCH`, `AGENTBENCH_LOG_LLM_MESSAGES`, `AGENTBENCH_LLM_LOG_MAX_CHARS`, `AGENTBENCH_FULL_LOGS`, `AGENTBENCH_`-prefixed settings (see `AgentBenchSettings`).
- Default docker image often `python:3.11-slim`; runner hardens network (bridge for setup, none for tests).

## What Happens in a Typical Agent Run
1) Load task YAML → validate schema/version → resolve repo URL.  
2) Baseline validation (unless skipped): clone/checkout, run setup (normalized pip), run tests expecting failure, record failure signature and rerun for flakiness.  
3) Instantiate sandbox and agent; emit events.  
4) LLM agent builds observation, calls tools (`list_files`/`read_file`/`search`/`apply_patch`/`run`); `AgentLoop` auto-runs tests after patches and before exit if needed.  
5) Stop on success, budget exhaustion, repeated identical failures, tool/LLM errors, or interrupts; map to `FailureReason`.  
6) Write AttemptRecord + artifacts (diffs, logs, events, optional llm_messages) under `artifacts/agent_runs/<task>/`.  
7) Reporting CLI can summarize attempts into markdown/CSV.

## Sample Artifacts (captured in this repo)
- **Baseline suite attempts** (`artifacts/runs/2026-01-06_11-45-33__custom-dev__baseline/logs/attempts.jsonl`): each line is an `AttemptRecord`. Example line for `toy_fail_pytest` baseline:
  ```json
  {"run_id":"01KEA364X90Y8VW59AB00AE9J8","task_id":"toy_fail_pytest","suite":"custom-dev","duration_sec":0.333887,"baseline_validation":{"attempted":true,"failed_as_expected":false,"exit_code":126},"result":{"passed":false,"exit_code":126,"failure_reason":"SETUP_FAILED"},"artifact_paths":{"setup_stdout":"artifacts/runs/2026-01-06_11-45-33__custom-dev__baseline/logs/toy_fail_pytest/setup_stdout.txt","setup_stderr":"artifacts/runs/2026-01-06_11-45-33__custom-dev__baseline/logs/toy_fail_pytest/setup_stderr.txt"}}
  ```
  Shows how setup failures are recorded and where stdout/stderr live.
- **Agent attempt log** (`artifacts/agent_runs/toy_fail_pytest/attempts.jsonl`): failed baseline clone example:
  ```json
  {"run_id":"01KE135MAYGEZHVAGB7RKE1WT8","task_id":"toy_fail_pytest","result":{"passed":false,"exit_code":128,"failure_reason":"GIT_CLONE_FAILED"},"artifact_paths":{"clone_stdout":"artifacts/agent_runs/toy_fail_pytest/logs/git_clone_stdout.txt","clone_stderr":"artifacts/agent_runs/toy_fail_pytest/logs/git_clone_stderr.txt"}}
  ```
- **Agent events** (`artifacts/agent_runs/toy_fail_pytest/events.jsonl`): chronological events during an LLM attempt:
  ```
  {"event_type":"tests_started","payload":{"command":"PYTHONPATH=/workspace/site-packages python -m pytest -q"}}
  {"event_type":"tests_finished","payload":{"exit_code":1,"passed":false,"stdout_path":"artifacts/agent_runs/toy_fail_pytest/logs/step_0001_stdout.txt","stderr_path":"artifacts/agent_runs/toy_fail_pytest/logs/step_0001_stderr.txt"}}
  {"event_type":"tool_call_started","payload":{"request_id":"call_0c9de05d53874a26b8358818","tool":"list_files","params":{"root":"/workspace","glob":"*"}}}
  {"event_type":"tool_call_finished","payload":{"request_id":"call_0c9de05d53874a26b8358818","tool":"list_files","status":"success","duration_sec":0.000502}}
  ```
  Demonstrates event schema and linking to log paths.
- **Baseline failure signatures** (`artifacts/agent_runs/toy_fail_pytest/logs/baseline_failure_signature.txt`): captures hash or nodeids of failing tests, e.g. `sha256:c3ed85...`. Rerun comparison (`baseline_rerun_comparison.txt`) shows repeated signatures:
  ```
  run_1_exit_code: 1
  run_1_signature: sha256:c3ed85aac704b1f05bb4b145d067a6e79af464c0ed40e402bae427f8e483ae8b
  run_2_exit_code: 1
  run_2_signature: sha256:c3ed85aac704b1f05bb4b145d067a6e79af464c0ed40e402bae427f8e483ae8b
  ```
  Used to detect flaky baselines in `validate_baseline`.
- **Patch artifacts** (`artifacts/tmp_patch.diff`, `tmp_patch_noeof.diff`, `tmp_patch_fixed.diff`): example unified diffs generated during development; live agent runs write per-step patches under `diffs/step_XXXX.patch`.

## Additional Nuanced Behaviors & Design Choices
- `AgentLoop._needs_setup_for_command` reruns setup if the agent launches pytest-like commands after patches and setup was invalidated.
- Success is only declared when the exact test command (normalized) returns exit code 0; arbitrary commands cannot short-circuit success (`_is_test_command` guard).
- Repeated identical failure detection: if the last N (`repeated_failure_threshold`) RUN outputs match, loop stops with `StopReason.REPEATED_FAILURE`.
- `validate_baseline` writes `baseline_failure_signature.txt` (hash or nodeid list) and `baseline_rerun_signature.txt` to detect flaky baselines; mismatches produce `BASELINE_FLAKY`.
- `validation.expected_*` fields let tasks assert specific failing tests or stderr/stdout patterns; mismatches emit `baseline_expectation_mismatch.txt` and `FailureReason.BASELINE_MISMATCH`.
- `FailureReason.precedence` ensures earlier pipeline failures (git/checkout/setup) override later ones (tests) in reporting.
- `tools.patching._normalize_patch_paths` auto-adds `repo/` or `src/` prefixes when the model emits bare paths; `_normalize_noeof_markers` injects missing “\ No newline at end of file” markers to make patches apply.
- `tools.search` treats ripgrep exit code 1 as “no matches” (not an error); other non-zero codes surface as `ripgrep_error`.
- `PersistentDockerSandbox` toggles container network between bridge/none per command, enabling controlled connectivity for setup vs tests.
- `util.jsonl.append_jsonl` uses file locks and fsync to make event/attempt logs crash-safe.
