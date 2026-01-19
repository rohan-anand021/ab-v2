# SWE-bench utilities

- `import_swebench.py`: Imports SWE-bench Lite from Hugging Face, filters for “fast” tasks, and emits AgentBench-compatible `task.yaml` files with default setup/run commands. Requires the `datasets` package to load the dataset.
- `swebench_smoke.yaml`: JSON-as-YAML config used by the Docker smoke script to run a single SWE-bench-lite instance end-to-end (clone → checkout → setup → run baseline tests expected to fail).
- `show_swebench_sample.py`: Prints a single SWE-bench Lite record (instance_id, repo, base_commit, FAIL_TO_PASS) to stdout for quick inspection. Requires `datasets`.
- `swebench_smoke_astropy.yaml`: Alternate smoke config for `astropy__astropy-12907`, including `environment_setup_commit`, `version`, FAIL_TO_PASS, and PASS_TO_PASS lists.
