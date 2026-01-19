# Sandbox scripts

- `docker-tests/`: Shell helpers and utilities for exercising the runner-core image (smoke sessions, offline clone/checkout, SWE-bench smoke, and a finder that scans SWE-bench Lite for a runnable instance).
- `docker-python-tests/`: Python-level smoke tests against the sandbox modules (docker client wrapper, compat helpers, session runner).
- `snippets.py`: Shared inline script fragments used by compat helpers (e.g., collections.abc rewrite).
