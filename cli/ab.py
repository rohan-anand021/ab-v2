from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import yaml

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sandbox.logger import EventLogger
from sandbox.models import RepoSpec, SandboxConfig, TaskSpec
from sandbox.report import RunRecorder
from sandbox.session import SessionRunner


app = typer.Typer(add_completion=False, help="ab sandbox CLI")


def load_instance(cfg_path: Path) -> dict:
    data = yaml.safe_load(cfg_path.read_text())
    instances = data.get("instances") or []
    if not instances:
        raise typer.Exit(code=1, message="No instances defined in config.")
    return instances[0]


def build_run_dir(artifacts_root: Path, repo_url: str) -> Path:
    repo_name = Path(repo_url).stem
    run_id = f"{repo_name}-{datetime.now().isoformat().replace(':', '-')}"
    run_dir = artifacts_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


@app.callback(invoke_without_command=True)
def main(
    config: Path = typer.Option(..., "--config", help="Path to instance YAML (one instance)."),
    artifacts_dir: Optional[Path] = typer.Option(Path("artifacts"), help="Root artifacts directory"),
) -> None:
    """Validate a task config by running clone/checkout/setup/test inside the sandbox."""
    if not config.is_file():
        raise typer.Exit(code=1, message=f"Config not found: {config}")

    inst = load_instance(config)
    run_dir = build_run_dir(artifacts_dir, inst["repo_url"])
    events_path = run_dir / "events.log"
    logger = EventLogger(events_path, name="ab", echo=True)

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
    test_patch = inst.get("test_patch", "")

    runner = SessionRunner(sandbox_cfg, logger=logger)
    with RunRecorder(run_dir) as recorder:
        report = runner.run(repo, task, test_patch=test_patch)
        report_path = recorder.save(report, events_path=events_path)
        if report.success:
            typer.secho(f"SUCCESS: see {report_path}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"FAILURE: see {report_path}", fg=typer.colors.RED)
            raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
