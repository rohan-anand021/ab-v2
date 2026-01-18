# Runtime Plan Generator for SWE-bench Tasks

Goal: automatically synthesize a task-specific runtime plan (base image + setup commands + test command) so a SWE-bench repo clones, checks out, installs cleanly, and the target tests fail for the expected reasons.

## Outline
- Static parse pass:
  - Read `pyproject.toml`, `setup.cfg`, `setup.py`, `requirements*.txt`, lockfiles (`poetry.lock`, `Pipfile.lock`), `tox.ini`, CI configs.
  - Infer Python version hints (`.python-version`, classifiers, `tool.poetry.dependencies.python`, `runtime.txt`).
  - Detect dev/test dependencies (extras, `requirements/dev.txt`, `tox` envs).
  - Flag known problem packages on Py3.11+ (ancient `pytest`/`py`, Flask 2.0 era needing Werkzeug/Jinja2/etc pins, `collections.MutableMapping` rewrites, setuptools caps).

- Plan synthesis:
  - Choose base image: default python:3.11-slim; downgrade if repo hints <3.9.
  - Build setup commands:
    - `python -m pip install -U pip setuptools wheel` (optionally cap setuptools when legacy deps present).
    - Install deps via lockfile if present; else `pip install -r requirements.txt` or `pip install .[dev,test]`.
    - Apply compatibility pins from heuristics (e.g., Flask 2.0.x pins, bump pytest/py, add setuptools_scm).
  - Optional pre-install patch: rewrite `collections.MutableMapping/Mapping` to `collections.abc.*` when needed.

- Validation loop (in throwaway container):
  - Run clone/checkout.
  - Run setup commands; on failure, parse error and apply known fixes (pin setuptools, add legacy deps, downgrade Python).
  - Ensure tests run and fail for expected reasons (non-zero from targeted tests, not import/build errors).

- Emit task spec:
  - Output `setup_commands`, `test_command`, `python_version`/base image, and any patches. Use this to populate smoke config or task YAML.

## Error-handling heuristics (examples)
- `ImportError: cannot import name 'MutableMapping'` → apply collections.abc rewrite before installs.
- `pkg_resources is deprecated` warnings causing failures → cap setuptools (e.g., `<81`) or suppress warnings in test command.
- `pytest/__spec__` or ancient `py` errors → bump `pytest`/`py` to modern versions.
- Missing `url_quote` in Werkzeug → pin Werkzeug/Jinja2/itsdangerous/click/MarkupSafe to 2.0.x for Flask 2.0 era.
- Build isolation pulling too-new setuptools → `pip install -U pip 'setuptools<CAP' wheel` before other installs; optionally `pip install --no-build-isolation -e .`.

## Constraints
- Prefer minimal, deterministic commands; avoid broad network variability (allow caches/mirrors if available).
- Keep the failure source to the intended tests; suppress or pin around unrelated warnings/errors.

## Next steps
- Implement a helper that:
  1) Parses repo metadata to propose Python version and pins.
  2) Generates setup/test commands.
  3) Tries them in a container and iterates on failures with heuristics.
  4) Emits the final plan for the smoke config or task YAML.
