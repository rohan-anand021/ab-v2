from __future__ import annotations

import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from sandbox.docker_client import DockerClient
from sandbox.logger import EventLogger
from sandbox.compat import apply_collections_rewrite, apply_pytest_cap, apply_setuptools_cap
from sandbox.models import (
    CommandResult,
    RepoSpec,
    RunReport,
    SandboxConfig,
    StageResult,
    StageStatus,
    TaskSpec,
)


def merge_env(base: Optional[Dict[str, str]], extra: Optional[Dict[str, str]]) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    if base:
        merged.update(base)
    if extra:
        merged.update(extra)
    return merged


class SessionRunner:
    def __init__(self, config: SandboxConfig, client: Optional[DockerClient] = None, logger: Optional[EventLogger] = None):
        self.config = config
        self.logger = logger
        self.client = client or DockerClient(timeout_sec=config.tool_timeout_sec, logger=logger)

    def run(self, repo: RepoSpec, task: TaskSpec, test_patch: str = "") -> RunReport:
        now = datetime.now().astimezone()
        report = RunReport(
            sandbox=self.config.model_dump(),
            repo=repo.model_dump(),
            task=task.model_dump(),
            stages=[],
            started_at=now,
            success=False,
        )
        container = self.config.container_name or f"sandbox-{uuid.uuid4().hex[:8]}"
        started = False

        def add_stage(name: str, status: StageStatus, commands: List[CommandResult], error: Optional[str] = None):
            report.stages.append(
                StageResult(
                    name=name,
                    status=status,
                    commands=commands,
                    error=error,
                )
            )

        try:
            start_res = self.client.run_container(
                image=self.config.image,
                name=container,
                workdir=self.config.workdir,
                env=self.config.env,
                network=self.config.network,
                detach=True,
            )
            if self.logger:
                self.logger.info("container start", stage="start", data={"exit": start_res.exit_code})
            started = start_res.exit_code == 0
            add_stage(
                "start",
                StageStatus.success if start_res.exit_code == 0 else StageStatus.failed,
                [start_res],
                None if start_res.exit_code == 0 else "container start failed",
            )
            if not started:
                report.completed_at = datetime.now().astimezone()
                return report

            clone_res = self.client.exec(
                container,
                ["bash", "-lc", f"cd {self.config.workdir} && git clone {repo.repo_url} repo"],
                env=self.config.env,
            )
            if self.logger:
                self.logger.info("clone", stage="clone", data={"exit": clone_res.exit_code})
            add_stage(
                "clone",
                StageStatus.success if clone_res.exit_code == 0 else StageStatus.failed,
                [clone_res],
                None if clone_res.exit_code == 0 else "clone failed",
            )
            if clone_res.exit_code != 0:
                report.completed_at = datetime.now().astimezone()
                return report

            checkout_res = self.client.exec(
                container,
                ["bash", "-lc", f"cd {self.config.workdir}/repo && git checkout {repo.commit}"],
                env=self.config.env,
            )
            if self.logger:
                self.logger.info("checkout", stage="checkout", data={"exit": checkout_res.exit_code})
            add_stage(
                "checkout",
                StageStatus.success if checkout_res.exit_code == 0 else StageStatus.failed,
                [checkout_res],
                None if checkout_res.exit_code == 0 else "checkout failed",
            )
            if checkout_res.exit_code != 0:
                report.completed_at = datetime.utcnow()
                return report

            if test_patch.strip():
                tmp_dir = Path(tempfile.mkdtemp(prefix="sandbox_patch_"))
                patch_path = tmp_dir / "patch.diff"
                patch_path.write_text(test_patch)
                write_res = self.client.cp(str(patch_path), f"{container}:/tmp/patch.diff")
                apply_res = self.client.exec(
                    container,
                    ["bash", "-lc", "cd /workspace/repo && patch -p1 < /tmp/patch.diff"],
                    env=self.config.env,
                )
                if self.logger:
                    self.logger.info("patch", stage="apply_patch", data={"exit": apply_res.exit_code})
                status = StageStatus.success if apply_res.exit_code == 0 else StageStatus.failed
                add_stage("apply_patch", status, [write_res, apply_res], None if status == StageStatus.success else "patch failed")
                if status != StageStatus.success:
                    report.completed_at = datetime.now().astimezone()
                    return report

            if repo.apply_compat:
                compat_exit = apply_collections_rewrite(self.client, container, workdir=f"{self.config.workdir}/repo", logger=self.logger)
                compat_res = CommandResult(
                    command="compat_collections_rewrite",
                    cwd=f"{self.config.workdir}/repo",
                    env=self.config.env,
                    exit_code=compat_exit,
                    stdout="",
                    stderr="",
                    duration_sec=0.0,
                    timed_out=False,
                )
                if self.logger:
                    self.logger.info("compat", stage="compat_rewrite", data={"exit": compat_res.exit_code})
                add_stage(
                    "compat_rewrite",
                    StageStatus.success if compat_exit == 0 else StageStatus.failed,
                    [compat_res],
                    None if compat_exit == 0 else "compat rewrite failed",
                )
                if compat_exit != 0:
                    report.completed_at = datetime.now().astimezone()
                    return report

            if repo.setuptools_cap:
                set_exit = apply_setuptools_cap(
                    self.client,
                    container,
                    version_cap=repo.setuptools_cap,
                    workdir=f"{self.config.workdir}/repo",
                    logger=self.logger,
                )
                set_res = CommandResult(
                    command=f"pip install {repo.setuptools_cap}",
                    cwd=f"{self.config.workdir}/repo",
                    env=self.config.env,
                    exit_code=set_exit,
                    stdout="",
                    stderr="",
                    duration_sec=0.0,
                    timed_out=False,
                )
                add_stage(
                    "compat_setuptools",
                    StageStatus.success if set_exit == 0 else StageStatus.failed,
                    [set_res],
                    None if set_exit == 0 else "setuptools cap failed",
                )
                if set_exit != 0:
                    report.completed_at = datetime.now().astimezone()
                    return report

            if repo.pytest_cap:
                py_exit = apply_pytest_cap(
                    self.client,
                    container,
                    version=repo.pytest_cap,
                    workdir=f"{self.config.workdir}/repo",
                    logger=self.logger,
                )
                py_res = CommandResult(
                    command=f"pip install pytest=={repo.pytest_cap}",
                    cwd=f"{self.config.workdir}/repo",
                    env=self.config.env,
                    exit_code=py_exit,
                    stdout="",
                    stderr="",
                    duration_sec=0.0,
                    timed_out=False,
                )
                add_stage(
                    "compat_pytest",
                    StageStatus.success if py_exit == 0 else StageStatus.failed,
                    [py_res],
                    None if py_exit == 0 else "pytest pin failed",
                )
                if py_exit != 0:
                    report.completed_at = datetime.now().astimezone()
                    return report

            setup_commands = task.setup_commands or []
            setup_results: List[CommandResult] = []
            setup_status = StageStatus.success
            for cmd in setup_commands:
                cmd_res = self.client.exec(
                    container,
                    ["bash", "-lc", f"cd {self.config.workdir}/repo && {cmd}"],
                    env=merge_env(self.config.env, task.env),
                )
                setup_results.append(cmd_res)
                if cmd_res.exit_code != 0 or cmd_res.timed_out:
                    setup_status = StageStatus.failed
                    break
            if self.logger:
                self.logger.info("setup", stage="setup", data={"exit": setup_results[-1].exit_code if setup_results else None})
            add_stage("setup", setup_status, setup_results, None if setup_status == StageStatus.success else "setup failed")
            if setup_status != StageStatus.success:
                report.completed_at = datetime.now().astimezone()
                return report

            test_res = self.client.exec(
                container,
                ["bash", "-lc", f"cd {self.config.workdir}/repo && {task.test_command}"],
                env=merge_env(self.config.env, task.env),
            )
            expected_fail = task.expected_fail
            passed = (test_res.exit_code != 0) if expected_fail else (test_res.exit_code == 0)
            if self.logger:
                self.logger.info(
                    "test",
                    stage="test",
                    data={"exit": test_res.exit_code, "expected_fail": expected_fail, "passed": passed},
                )
            add_stage(
                "test",
                StageStatus.success if passed else StageStatus.failed,
                [test_res],
                None if passed else "test outcome did not match expectation",
            )
            report.success = passed
            report.completed_at = datetime.now().astimezone()
            return report
        finally:
            if started:
                self.client.stop(container)
                self.client.rm(container)
