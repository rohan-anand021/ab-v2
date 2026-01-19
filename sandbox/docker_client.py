from __future__ import annotations

import subprocess
import shlex
import time
from typing import Dict, List, Optional

from sandbox.logger import EventLogger
from sandbox.models import CommandResult


class DockerClient:
    def __init__(self, timeout_sec: int = 120, logger: Optional[EventLogger] = None):
        self.timeout_sec = timeout_sec
        self.logger = logger

    def _run(
        self,
        args: List[str],
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> CommandResult:
        start = time.time()
        proc = None
        try:
            proc = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout or self.timeout_sec,
                env=env,
                cwd=cwd,
            )
            duration = time.time() - start
            return CommandResult(
                command=" ".join(shlex.quote(a) for a in args),
                cwd=cwd,
                env=env or {},
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_sec=duration,
                timed_out=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.time() - start
            stdout = exc.stdout if exc.stdout else ""
            stderr = exc.stderr if exc.stderr else ""
            return CommandResult(
                command=" ".join(shlex.quote(a) for a in args),
                cwd=cwd,
                env=env or {},
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_sec=duration,
                timed_out=True,
            )
        finally:
            if self.logger:
                self.logger.info(
                    "docker command finished",
                    stage="docker",
                    data={
                        "command": " ".join(shlex.quote(a) for a in args),
                        "exit_code": proc.returncode if proc else None,
                        "timed_out": proc is None,
                    },
                )

    def run_container(
        self,
        image: str,
        name: Optional[str] = None,
        workdir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        network: Optional[str] = None,
        detach: bool = True,
        cmd: Optional[List[str]] = None,
    ) -> CommandResult:
        args = ["docker", "run"]
        if detach:
            args.append("-d")
        if name:
            args += ["--name", name]
        if workdir:
            args += ["-w", workdir]
        if env:
            for k, v in env.items():
                args += ["-e", f"{k}={v}"]
        if network:
            args += ["--network", network]
        args.append(image)
        if cmd:
            args += cmd
        return self._run(args)

    def exec(
        self,
        container: str,
        command: List[str],
        workdir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> CommandResult:
        args = ["docker", "exec"]
        if workdir:
            args += ["-w", workdir]
        if env:
            for k, v in env.items():
                args += ["-e", f"{k}={v}"]
        args.append(container)
        args += command
        return self._run(args, timeout=timeout)

    def cp(self, src: str, dest: str) -> CommandResult:
        args = ["docker", "cp", src, dest]
        return self._run(args)

    def stop(self, container: str) -> CommandResult:
        return self._run(["docker", "stop", container])

    def rm(self, container: str, force: bool = True) -> CommandResult:
        args = ["docker", "rm"]
        if force:
            args.append("-f")
        args.append(container)
        return self._run(args)
