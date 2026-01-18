# Docker test scripts

- `runner_core_session_smoke.sh`: Builds confidence in the runner-core base image and session contract: container start/stop, repeated execs, stdout/stderr capture, exit codes, default cwd (/workspace), env overlay, tool presence (rg/git/patch/uv), patch application inside /workspace, and timeout killing a long-running process.
- `runner_core_local_clone_checkout.sh`: No-network git clone/checkout integration: host creates a tiny repo with failing and passing commits, copies a bare repo into the container, installs a minimal pytest shim (offline), clones/checkout inside /workspace, and verifies pytest fails on commit A and passes on commit B.
- `runner_core_swebench_smoke.sh`: Manual SWE-bench-lite one-instance smoke (networked): reads `swebench_smoke.yaml` for repo/commit/test info, starts a runner-core container, clones the repo, checks out the commit, runs optional setup commands, and asserts the baseline test command fails.

## Config files

- `swebench_smoke.yaml`: Small JSON-as-YAML list of SWE-bench-lite instances for manual smoke tests. Fill in the base commit and FAIL_TO_PASS-derived test command for at least one instance (e.g., `psf__requests-1963`). The smoke script consumes this file.
