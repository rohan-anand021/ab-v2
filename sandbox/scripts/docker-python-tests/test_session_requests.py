from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.append(str(Path(__file__).resolve().parents[3]))

from sandbox.logger import EventLogger
from sandbox.models import RepoSpec, SandboxConfig, TaskSpec
from sandbox.report import RunRecorder
from sandbox.session import SessionRunner


def load_instance(path: Path) -> dict:
    data = yaml.safe_load(path.read_text())
    instances = data.get("instances") or []
    if not instances:
        raise SystemExit("No instances in config")
    return instances[0]


def main() -> int:
    cfg_path = Path("scripts/swe-bench/swebench_smoke_requests.yaml")
    inst = load_instance(cfg_path)
    repo_name = Path(inst["repo_url"]).stem
    run_dir = Path("artifacts") / f"{repo_name}-{datetime.now().isoformat().replace(':', '-')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    sandbox_cfg = SandboxConfig()
    repo = RepoSpec(
        repo_url=inst["repo_url"],
        commit=inst["commit"],
        apply_compat=True,
        setuptools_cap=inst.get("setuptools_cap"),
        pytest_cap=inst.get("pytest_cap"),
    )
    task = TaskSpec(
        setup_commands=inst.get("setup_commands", []),
        test_command=inst["test_command"],
        expected_fail=inst.get("expected_fail", True),
        env=inst.get("env", {}),
    )
    events_path = run_dir / "session_events.log"
    logger = EventLogger(events_path, name="session_test", echo=False)
    runner = SessionRunner(sandbox_cfg, logger=logger)
    with RunRecorder(run_dir) as recorder:
        report = runner.run(repo, task, test_patch=inst.get("test_patch", ""))
        recorder.save(report, events_path=events_path)
        return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
